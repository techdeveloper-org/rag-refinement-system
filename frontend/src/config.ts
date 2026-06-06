/**
 * Runtime configuration sourced from Vite environment variables (12-factor;
 * never hardcode secrets). The JWT bearer token is read from session storage,
 * populated by the OAuth2 authorization-code flow (ADR-7) which is delegated to
 * the external provider, not implemented in this SPA.
 */

const TOKEN_STORAGE_KEY = "rag_refinement_jwt";

/** Resolve the API base URL from the build-time env, defaulting to local dev. */
export function apiBaseUrl(): string {
  const fromEnv = import.meta.env["VITE_API_BASE_URL"];
  return typeof fromEnv === "string" && fromEnv.length > 0 ? fromEnv : "http://localhost:8000";
}

/**
 * Read the current JWT bearer token from session storage.
 *
 * @returns The token string, or null when no session is established.
 */
export function getSessionToken(): string | null {
  try {
    return globalThis.sessionStorage?.getItem(TOKEN_STORAGE_KEY) ?? null;
  } catch {
    return null;
  }
}

/** Persist a JWT bearer token to session storage (post OAuth2 redirect). */
export function setSessionToken(token: string): void {
  try {
    globalThis.sessionStorage?.setItem(TOKEN_STORAGE_KEY, token);
  } catch {
    // Storage unavailable (private mode / SSR): token simply not persisted.
  }
}
