import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routers import admin, categories, chat, connections, facts, internal, pending, settings, status, tenants
from src.core.log import log

app = FastAPI(title="Anamnesis API")

# Local dev only — the Vite dev server's own origin. Harmless in
# production: the built frontend is served from this same
# origin there (see the StaticFiles mount at the bottom of this file), so
# the browser never even sends a cross-origin request for the CORS
# headers below to matter.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# What the page loads: its own files, plus Google sign-in (script, its iframe,
# its styles and requests). It ran report-only first and the live
# app showed no violation, so it is enforced. If a new page needs another
# source, add it here; the browser console names what was refused.
_CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self' https://accounts.google.com/gsi/client",
        "frame-src https://accounts.google.com/gsi/",
        "connect-src 'self' https://accounts.google.com/gsi/",
        "style-src 'self' 'unsafe-inline' https://accounts.google.com/gsi/style",
        # The profile photo comes from Google.
        "img-src 'self' data: https://*.googleusercontent.com",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "object-src 'none'",
    ]
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = _CONTENT_SECURITY_POLICY
    return response


@app.middleware("http")
async def log_request_duration(request: Request, call_next):
    """One line per REST call: how long the server took to answer.

    Only the path is logged, never the query string. CORS preflights are
    skipped as noise, and the chat WebSocket isn't an HTTP request (it stays
    open for a whole conversation, so a duration would mean nothing).
    """
    started = time.perf_counter()
    response = await call_next(request)
    if request.method != "OPTIONS":
        elapsed_ms = (time.perf_counter() - started) * 1000
        log(
            "INFO",
            "request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round(elapsed_ms),
        )
    return response


app.include_router(internal.router)
app.include_router(categories.router)
app.include_router(settings.router)
app.include_router(admin.router)
app.include_router(connections.router)
app.include_router(tenants.router)
app.include_router(facts.router)
app.include_router(status.router)
app.include_router(pending.router)
app.include_router(chat.router)


# Registered last on purpose: Starlette only falls through to a mount once
# no route above it has already matched the path, so this can never shadow
# an API route above. Only present in the production image —
# the Dockerfile bakes the React build in here; local dev keeps using the
# separate Vite dev server instead, so this directory won't exist there.
_FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend_dist"
if _FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=_FRONTEND_DIST, html=True), name="frontend")
