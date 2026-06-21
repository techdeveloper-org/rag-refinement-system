"""Authentication, tenant resolution, and API-key store (STORY-038, ADR-7).

Two credential types resolve to one :class:`Principal` carrying a
``tenant_id``:

* Enterprise: ``X-API-Key`` header. Keys are verified against a hashed-at-rest
  store - the plaintext key is never persisted. Hashing is salted with
  ``API_KEY_SALT`` (HMAC-SHA-256). Rotation invalidates the old hash.
* Personal tool: ``Authorization: Bearer <jwt>``. The JWT is validated for
  signature, expiry, and audience using ``JWT_SECRET``; ``alg=none`` is
  rejected by pinning the allowed algorithm.

The resolved ``tenant_id`` is the row-level IDOR guard substrate: every
document query filters on it so a caller can never read another tenant's data
(AGREED CONTRACT python-backend-engineer <-> database-engineer; OAQ-5).
"""

from __future__ import annotations

import enum
import hashlib
import hmac
import threading
from dataclasses import dataclass

import jwt
from fastapi import Request

from backend.app.errors import unauthorized
from backend.app.settings import Settings, get_settings


class PrincipalKind(enum.StrEnum):
    """The credential class a principal authenticated with."""

    API_KEY = "api_key"
    JWT = "jwt"


@dataclass(frozen=True)
class Principal:
    """An authenticated caller resolved from a credential.

    Attributes:
        tenant_id: Owning tenant; the IDOR-guard filter key.
        subject: Stable principal id (API-key id or JWT subject).
        kind: Whether the caller used an API key or a JWT.
        rate_limit_key: Per-credential bucket key for rate limiting.
    """

    tenant_id: str
    subject: str
    kind: PrincipalKind

    @property
    def rate_limit_key(self) -> str:
        """Return the per-credential rate-limit bucket key.

        Returns:
            A key combining the credential kind and subject so an API key and
            a JWT subject never share a bucket.
        """
        return f"{self.kind.value}:{self.subject}"


def hash_api_key(plaintext_key: str, salt: str) -> str:
    """Hash an API key for at-rest storage using salted HMAC-SHA-256.

    The plaintext key is never stored; only this digest is compared. Rotating
    a key changes its digest, so the previous digest no longer matches.

    Args:
        plaintext_key: The raw API key presented by the caller.
        salt: The ``API_KEY_SALT`` secret.

    Returns:
        A hex-encoded HMAC-SHA-256 digest of the key.
    """
    return hmac.new(
        salt.encode("utf-8"), plaintext_key.encode("utf-8"), hashlib.sha256
    ).hexdigest()


@dataclass(frozen=True)
class ApiKeyRecord:
    """A registered API key entry in the hashed-at-rest store.

    Attributes:
        key_hash: Salted HMAC digest of the plaintext key.
        tenant_id: Tenant the key authenticates.
        subject: Stable key identifier (e.g. ``key_<id>``).
        active: False once the key has been rotated/revoked.
    """

    key_hash: str
    tenant_id: str
    subject: str
    active: bool = True


class ApiKeyStore:
    """In-memory hashed API-key store with rotation support.

    Only digests are held; the plaintext key is supplied at registration time,
    hashed immediately, and discarded. Replaced production stores back this
    with Postgres but expose the same interface.

    **Multi-replica limitation:** This store lives entirely in process memory. In a
    multi-replica deployment (e.g. Kubernetes with replicas > 1) each pod holds its
    own independent store, so a key registered against one replica is invisible to
    the others. For production multi-replica deployments, replace this class with a
    database-backed implementation that reads key digests from Postgres.
    """

    def __init__(self, salt: str) -> None:
        """Initialize an empty store.

        Args:
            salt: The ``API_KEY_SALT`` used to hash all keys.
        """
        self._salt = salt
        self._records: dict[str, ApiKeyRecord] = {}
        self._lock = threading.Lock()

    def register(self, plaintext_key: str, tenant_id: str, subject: str) -> None:
        """Register a new key by storing only its salted digest.

        Args:
            plaintext_key: The raw key to register (not persisted).
            tenant_id: Tenant the key authenticates.
            subject: Stable key identifier.
        """
        digest = hash_api_key(plaintext_key, self._salt)
        with self._lock:
            self._records[digest] = ApiKeyRecord(
                key_hash=digest, tenant_id=tenant_id, subject=subject, active=True
            )

    def rotate(self, old_plaintext_key: str, new_plaintext_key: str) -> None:
        """Rotate a key: deactivate the old digest, register the new one.

        Args:
            old_plaintext_key: The key being retired.
            new_plaintext_key: The replacement key.

        Raises:
            KeyError: If the old key is not registered.
        """
        old_digest = hash_api_key(old_plaintext_key, self._salt)
        new_digest = hash_api_key(new_plaintext_key, self._salt)
        with self._lock:
            record = self._records.get(old_digest)
            if record is None:
                raise KeyError("unknown api key")
            del self._records[old_digest]
            self._records[new_digest] = ApiKeyRecord(
                key_hash=new_digest, tenant_id=record.tenant_id, subject=record.subject, active=True
            )

    def resolve(self, plaintext_key: str) -> ApiKeyRecord | None:
        """Resolve an active key record from a presented plaintext key.

        Iterates all records using :func:`hmac.compare_digest` to prevent
        timing side-channel attacks that could enumerate registered digests.

        Args:
            plaintext_key: The raw key presented by the caller.

        Returns:
            The matching active record, or None if unknown/rotated.
        """
        digest = hash_api_key(plaintext_key, self._salt)
        found: ApiKeyRecord | None = None
        with self._lock:
            for record in self._records.values():
                if hmac.compare_digest(digest, record.key_hash) and record.active:
                    found = record
        return found


_api_key_store: ApiKeyStore | None = None
_api_key_store_lock = threading.Lock()


def get_api_key_store() -> ApiKeyStore:
    """Return the process-wide API-key store, creating it on first use.

    Uses double-checked locking to ensure thread-safe singleton
    initialization without acquiring the lock on every call.

    Returns:
        The shared :class:`ApiKeyStore` salted with ``API_KEY_SALT``.

    Raises:
        ProblemException: 401 when ``API_KEY_SALT`` is not configured.
    """
    global _api_key_store
    if _api_key_store is None:
        with _api_key_store_lock:
            if _api_key_store is None:
                settings = get_settings()
                if not settings.api_key_salt:
                    raise unauthorized("API key authentication is not configured.")
                _api_key_store = ApiKeyStore(settings.api_key_salt)
    return _api_key_store


def _decode_jwt(token: str, settings: Settings) -> dict[str, object]:
    """Decode and validate a JWT (signature, expiry, audience).

    The allowed algorithm is pinned from settings so ``alg=none`` and
    algorithm-confusion attacks are rejected.

    Args:
        token: The bearer token value.
        settings: Resolved application settings holding the JWT secret.

    Returns:
        The validated token claims.

    Raises:
        ProblemException: 401 on any signature/expiry/audience failure.
    """
    if not settings.jwt_secret:
        raise unauthorized("Bearer authentication is not configured.")
    if not settings.jwt_issuer:
        raise unauthorized(
            "Bearer authentication requires JWT_ISSUER to be configured."
        )
    try:
        required_claims = ["exp", "sub"]
        if settings.jwt_issuer:
            required_claims.append("iss")
        if settings.jwt_audience:
            required_claims.append("aud")
        options = {"require": required_claims}
        decode_kwargs: dict[str, object] = {}
        if settings.jwt_audience:
            decode_kwargs["audience"] = settings.jwt_audience
        if settings.jwt_issuer:
            decode_kwargs["issuer"] = settings.jwt_issuer
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options=options,  # type: ignore[arg-type]
            **decode_kwargs,  # type: ignore[arg-type]
        )
    except jwt.PyJWTError as exc:
        raise unauthorized("Bearer token is invalid or expired.") from exc
    return claims


def _resolve_jwt_principal(token: str, settings: Settings) -> Principal:
    """Resolve a JWT bearer token into a principal.

    Args:
        token: The bearer token value.
        settings: Resolved application settings.

    Returns:
        A :class:`Principal` of kind JWT.

    Raises:
        ProblemException: 401 when the token is invalid or lacks a tenant.
    """
    claims = _decode_jwt(token, settings)
    subject = str(claims.get("sub", ""))
    if "tenant_id" in claims and claims["tenant_id"] is not None:
        tenant_id: object = claims["tenant_id"]
    elif "tid" in claims and claims["tid"] is not None:
        tenant_id = claims["tid"]
    else:
        tenant_id = None
    if not subject or tenant_id is None:
        raise unauthorized("Bearer token is missing required claims.")
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise unauthorized("Bearer token tenant_id claim must be a non-empty string.")
    return Principal(
        tenant_id=tenant_id, subject=subject, kind=PrincipalKind.JWT
    )


def _resolve_api_key_principal(api_key: str) -> Principal:
    """Resolve an API key into a principal via the hashed store.

    Args:
        api_key: The raw ``X-API-Key`` value.

    Returns:
        A :class:`Principal` of kind API_KEY.

    Raises:
        ProblemException: 401 when the key is unknown or rotated out.
    """
    record = get_api_key_store().resolve(api_key)
    if record is None:
        raise unauthorized("API key is missing or invalid.")
    if not isinstance(record.tenant_id, str) or not record.tenant_id.strip():
        raise unauthorized("API key tenant_id is not a valid non-empty string.")
    return Principal(
        tenant_id=record.tenant_id,
        subject=record.subject,
        kind=PrincipalKind.API_KEY,
    )


def resolve_principal(request: Request, settings: Settings) -> Principal:
    """Resolve the authenticated principal from request credentials.

    Precedence: ``X-API-Key`` (enterprise) is checked first, then the
    ``Authorization: Bearer`` JWT (personal tool). Exactly one credential is
    required; absence of both is a 401.

    Args:
        request: The incoming request.
        settings: Resolved application settings.

    Returns:
        The resolved :class:`Principal` carrying ``tenant_id``.

    Raises:
        ProblemException: 401 when no valid credential is present.
    """
    api_key = request.headers.get("X-API-Key")
    if api_key:
        if not settings.api_key_salt:
            raise unauthorized("API key authentication is not configured.")
        return _resolve_api_key_principal(api_key)

    authorization = request.headers.get("Authorization")
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        if token:
            return _resolve_jwt_principal(token, settings)

    raise unauthorized()


def require_principal(request: Request) -> Principal:
    """FastAPI dependency that authenticates and returns the principal.

    Args:
        request: The incoming request (injected by FastAPI).

    Returns:
        The resolved :class:`Principal`.

    Raises:
        ProblemException: 401 when authentication fails.
    """
    return resolve_principal(request, get_settings())
