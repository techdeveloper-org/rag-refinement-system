"""Security package: auth, tenant scoping, and rate limiting (STORY-038).

Implements ADR-7 authentication (API keys for enterprise, OAuth2/JWT for the
personal tool), the tenant_id resolution substrate that the IDOR guard and
targeted retrieval depend on (NFR-015), and the per-credential rate-limit
dependency (ADV-003). Secrets are read from the environment only - no key
material is defaulted in source.
"""

from __future__ import annotations

from backend.app.security.auth import (
    Principal,
    PrincipalKind,
    hash_api_key,
    require_principal,
)
from backend.app.security.rate_limit import RateLimiter, get_rate_limiter, rate_limit

__all__ = [
    "Principal",
    "PrincipalKind",
    "hash_api_key",
    "require_principal",
    "RateLimiter",
    "get_rate_limiter",
    "rate_limit",
]
