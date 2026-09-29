// In dev, the Vite dev server (this file) and the FastAPI backend run as
// separate processes on different ports (see docker-compose.yml), so calls
// need an absolute URL. In production the backend serves this same built
// frontend from one origin, so relative paths (same origin,
// no CORS) are both simpler and correct.
export const API_BASE = import.meta.env.DEV ? "http://localhost:8010" : "";

// The server refused the request because this account isn't allowed in at
// all (not on the allowlist, or an unverified email) — not a network failure,
// so retrying can't help.
export class ForbiddenError extends Error {}
