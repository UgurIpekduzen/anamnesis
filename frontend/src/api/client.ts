// In dev, the Vite dev server (this file) and the FastAPI backend run as
// separate processes on different ports (see docker-compose.yml), so calls
// need an absolute URL. In production the backend serves this same built
// frontend from one origin (APPCE-56), so relative paths (same origin,
// no CORS) are both simpler and correct.
export const API_BASE = import.meta.env.DEV ? "http://localhost:8010" : "";
