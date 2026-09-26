import asyncio
import json
import os
import time
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from api.deps import get_current_owner_uid, verify_token
from api.routers import admin, categories, connections, internal, settings
from src.facts.categories import InvalidCategory
from src.projects.chat_history import append_turn, clear_turns, load_recent_turns
from src.facts.facts import delete_fact, get_fact, get_tenant_facts, update_fact
from src.facts.similar_facts import find_similar_facts
from src.integrations.status import get_project_github_status, get_project_jira_status
from src.accounts.settings import get_settings
from src.core.log import log
from src.projects.tenants import (
    TenantNameTaken,
    add_tenant,
    clear_github_repo,
    clear_jira_project_key,
    delete_tenant,
    get_owned_tenant,
    list_tenants,
    rename_tenant,
    set_github_repo,
    set_jira_project_key,
)
from src.accounts.usage import DailyLimitExceeded, record_message

# Token-cost guards (see APPCE-59). A message stays in the session history
# and is resent on every model call of the following turns, so an
# unbounded one is the most expensive input a user can send. A normal
# turn takes 3-4 model calls; ADK's own default cap is 500.
MAX_MESSAGE_CHARS = int(os.environ.get("MAX_MESSAGE_CHARS", 4000))
MAX_LLM_CALLS_PER_TURN = int(os.environ.get("MAX_LLM_CALLS_PER_TURN", 10))

# How many saved turns the UI loads when it opens a conversation. Bounds the
# Firestore reads of one history load (APPCE-60); the model's own memory is
# governed separately, by the user's history_turns setting.
CHAT_HISTORY_DISPLAY_TURNS = int(os.environ.get("CHAT_HISTORY_DISPLAY_TURNS", 50))

# The chat socket authenticates with its first frame (APPCE-67), so an
# unauthenticated connection is a resource an anonymous caller can hold:
# give it seconds, and a frame size no real token comes close to (a Google
# ID token is 1-2 KB).
AUTH_TIMEOUT_SECONDS = float(os.environ.get("WS_AUTH_TIMEOUT_SECONDS", 10))
MAX_AUTH_FRAME_CHARS = 8192

app = FastAPI(title="Anamnesis API")

# Local dev only — the Vite dev server's own origin. Harmless in
# production (APPCE-56): the built frontend is served from this same
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
# its styles and requests). It ran report-only first (APPCE-119) and the live
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
    """One line per REST call: how long the server took to answer (APPCE-68).

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


@app.get("/tenants")
def get_tenants(owner_uid: str = Depends(get_current_owner_uid)) -> list[dict]:
    return list_tenants(owner_uid)


class TenantCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(strict=True, min_length=1, max_length=200)


@app.post("/tenants")
def create_tenant(body: TenantCreate, owner_uid: str = Depends(get_current_owner_uid)) -> dict:
    # Project lifecycle (create/rename/delete) is deliberately UI-only, not
    # a chat tool — see agent/agent.py's build_agent docstring for why.
    try:
        tenant_id = add_tenant(body.name, owner_uid)
    except TenantNameTaken as exc:
        # The same answer whoever owns the existing project (APPCE-117).
        raise HTTPException(status_code=409, detail=f"{exc} Try another name.")
    return {"tenant_id": tenant_id}


class FactUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Omitted means unchanged, same as update_fact — but an empty body would
    # change nothing, so it is refused below.
    content: str | None = Field(default=None, strict=True, min_length=1, max_length=2000)
    category: str | None = Field(default=None, strict=True, min_length=1, max_length=50)


class TenantRename(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(strict=True, min_length=1, max_length=200)


@app.patch("/tenants/{tenant_id}")
def update_tenant(
    tenant_id: str, body: TenantRename, owner_uid: str = Depends(get_current_owner_uid)
) -> dict:
    try:
        rename_tenant(tenant_id, body.name, owner_uid)
    except PermissionError:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"status": "renamed"}


@app.delete("/tenants/{tenant_id}")
def remove_tenant(tenant_id: str, owner_uid: str = Depends(get_current_owner_uid)) -> dict:
    try:
        delete_tenant(tenant_id, owner_uid)
    except PermissionError:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"status": "deleted"}


# Which GitHub repo and Jira project a project is linked to is set here, in
# the UI, and not by the chat agent: these values decide whose repo gets polled
# with the user's token and what goes into a Jira query, and the agent reads
# text other people wrote (APPCE-107).
class GithubRepoUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    github_repo: str = Field(strict=True, min_length=1, max_length=140)


class JiraProjectKeyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jira_project_key: str = Field(strict=True, min_length=1, max_length=60)


@app.put("/tenants/{tenant_id}/github_repo")
def update_github_repo(
    tenant_id: str, body: GithubRepoUpdate, owner_uid: str = Depends(get_current_owner_uid)
) -> dict:
    try:
        set_github_repo(tenant_id, body.github_repo, owner_uid)
    except PermissionError:
        raise HTTPException(status_code=404, detail="Project not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"github_repo": body.github_repo}


@app.delete("/tenants/{tenant_id}/github_repo")
def remove_github_repo(tenant_id: str, owner_uid: str = Depends(get_current_owner_uid)) -> dict:
    try:
        clear_github_repo(tenant_id, owner_uid)
    except PermissionError:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"github_repo": None}


@app.put("/tenants/{tenant_id}/jira_project_key")
def update_jira_project_key(
    tenant_id: str, body: JiraProjectKeyUpdate, owner_uid: str = Depends(get_current_owner_uid)
) -> dict:
    try:
        set_jira_project_key(tenant_id, body.jira_project_key, owner_uid)
    except PermissionError:
        raise HTTPException(status_code=404, detail="Project not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"jira_project_key": body.jira_project_key}


@app.delete("/tenants/{tenant_id}/jira_project_key")
def remove_jira_project_key(tenant_id: str, owner_uid: str = Depends(get_current_owner_uid)) -> dict:
    try:
        clear_jira_project_key(tenant_id, owner_uid)
    except PermissionError:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"jira_project_key": None}


@app.get("/tenants/{tenant_id}/facts")
def get_facts(tenant_id: str, owner_uid: str = Depends(get_current_owner_uid)) -> list[dict]:
    return get_tenant_facts(tenant_id, owner_uid)


# What a chat proposal card's button calls (APPCE-107): the model only ever
# proposes an edit or a delete, and the user's click is what makes it.
@app.patch("/tenants/{tenant_id}/facts/{fact_id}")
def edit_fact(
    tenant_id: str, fact_id: str, body: FactUpdate, owner_uid: str = Depends(get_current_owner_uid)
) -> dict:
    if body.content is None and body.category is None:
        raise HTTPException(status_code=422, detail="Give a content or a category to change")
    try:
        get_fact(tenant_id, fact_id, owner_uid)
        update_fact(tenant_id, fact_id, owner_uid, content=body.content, category=body.category)
    except (PermissionError, LookupError):
        raise HTTPException(status_code=404, detail="Fact not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "updated"}


@app.delete("/tenants/{tenant_id}/facts/{fact_id}")
def remove_fact(tenant_id: str, fact_id: str, owner_uid: str = Depends(get_current_owner_uid)) -> dict:
    try:
        get_fact(tenant_id, fact_id, owner_uid)
        delete_fact(tenant_id, fact_id, owner_uid)
    except (PermissionError, LookupError):
        raise HTTPException(status_code=404, detail="Fact not found")
    return {"status": "deleted"}


# The Status panel (APPCE-110): what is open in the project's Jira project and
# GitHub repo, read live with the user's own credentials, no model involved.
@app.get("/tenants/{tenant_id}/jira_status")
def get_jira_status_endpoint(tenant_id: str, owner_uid: str = Depends(get_current_owner_uid)) -> dict:
    try:
        return get_project_jira_status(tenant_id, owner_uid)
    except PermissionError:
        raise HTTPException(status_code=404, detail="Project not found")


@app.get("/tenants/{tenant_id}/github_status")
def get_github_status_endpoint(tenant_id: str, owner_uid: str = Depends(get_current_owner_uid)) -> dict:
    try:
        return get_project_github_status(tenant_id, owner_uid)
    except PermissionError:
        raise HTTPException(status_code=404, detail="Project not found")


# Lazily-importing wrappers (APPCE-50, same pattern as get_runner/
# restore_session below): src.facts.pending_facts pulls in google-cloud-pubsub
# (via src.facts.publisher, for the approve path), which only these three
# endpoints need — deferring it keeps it off every other request's
# startup cost. Real module-level names so
# test/test_api_pending_facts.py's monkeypatch.setattr(api_main, ...)
# still works.
def list_pending_facts(tenant_id: str, owner_uid: str) -> list[dict]:
    from src.facts.pending_facts import list_pending_facts as _list_pending_facts

    return _list_pending_facts(tenant_id, owner_uid)


def approve_pending_fact(tenant_id: str, pending_fact_id: str, owner_uid: str) -> None:
    from src.facts.pending_facts import approve_pending_fact as _approve_pending_fact

    return _approve_pending_fact(tenant_id, pending_fact_id, owner_uid)


def reject_pending_fact(tenant_id: str, pending_fact_id: str, owner_uid: str) -> None:
    from src.facts.pending_facts import reject_pending_fact as _reject_pending_fact

    return _reject_pending_fact(tenant_id, pending_fact_id, owner_uid)


def get_pending_fact_stats(tenant_id: str, owner_uid: str) -> dict:
    from src.facts.pending_facts import get_pending_fact_stats as _get_pending_fact_stats

    return _get_pending_fact_stats(tenant_id, owner_uid)


@app.get("/tenants/{tenant_id}/pending_facts")
def get_pending_facts(tenant_id: str, owner_uid: str = Depends(get_current_owner_uid)) -> list[dict]:
    try:
        return list_pending_facts(tenant_id, owner_uid)
    except PermissionError:
        raise HTTPException(status_code=404, detail="Project not found")


@app.get("/tenants/{tenant_id}/pending_facts/stats")
def get_pending_facts_stats(tenant_id: str, owner_uid: str = Depends(get_current_owner_uid)) -> dict:
    try:
        return get_pending_fact_stats(tenant_id, owner_uid)
    except PermissionError:
        raise HTTPException(status_code=404, detail="Project not found")


@app.post("/tenants/{tenant_id}/pending_facts/{pending_fact_id}/approve")
def approve_pending_fact_endpoint(
    tenant_id: str, pending_fact_id: str, owner_uid: str = Depends(get_current_owner_uid)
) -> dict:
    try:
        approve_pending_fact(tenant_id, pending_fact_id, owner_uid)
    except PermissionError:
        raise HTTPException(status_code=404, detail="Project not found")
    except InvalidCategory as exc:
        # The user removed this fact's category after it was staged.
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError:
        raise HTTPException(status_code=404, detail="Pending fact not found")
    return {"status": "approved"}


@app.delete("/tenants/{tenant_id}/pending_facts/{pending_fact_id}")
def reject_pending_fact_endpoint(
    tenant_id: str, pending_fact_id: str, owner_uid: str = Depends(get_current_owner_uid)
) -> dict:
    try:
        reject_pending_fact(tenant_id, pending_fact_id, owner_uid)
    except PermissionError:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"status": "rejected"}


@app.get("/tenants/{tenant_id}/history")
def get_history(tenant_id: str, owner_uid: str = Depends(get_current_owner_uid)) -> list[dict]:
    try:
        return load_recent_turns(tenant_id, owner_uid, CHAT_HISTORY_DISPLAY_TURNS)
    except PermissionError:
        raise HTTPException(status_code=404, detail="Project not found")


_DONE = object()


async def _iterate_off_loop(generator):
    """Iterate a blocking generator without blocking the event loop.

    Runner.run is a sync generator: each next() waits on the model and on
    Firestore-backed tools. Called directly from the async handler that
    froze every other request on the server for the whole turn (APPCE-62);
    a worker thread per step keeps the loop free.
    """
    while True:
        item = await asyncio.to_thread(next, generator, _DONE)
        if item is _DONE:
            return
        yield item


async def _best_effort(func, *args, what: str) -> None:
    """Run a blocking, non-essential call off the event loop.

    Usage counting, saving and clearing history all touch Firestore
    (~0.3-1 s each, sequentially). None of them is worth breaking a
    conversation over, and none may stall the loop (APPCE-64), so they run
    in a worker thread and a failure is logged, not raised.
    """
    try:
        await asyncio.to_thread(func, *args)
    except Exception as exc:
        log("WARNING", "best_effort_failed", what=what, error=repr(exc))


# ADK's own name for the synthetic function call it generates when a
# require_confirmation=True tool is invoked (APPCE-91) — never a real tool
# in agent/agent.py's tools list, so it's filtered out of the Trace tab's
# tool_call/tool_result messages and handled separately (see chat() below).
_REQUEST_CONFIRMATION_FUNCTION_CALL_NAME = "adk_request_confirmation"


def _event_to_messages(event) -> list[dict]:
    # The id pairs a result with its call for the UI's Trace tab — matching
    # by tool name alone breaks as soon as the model calls one tool twice.
    messages = []
    for call in event.get_function_calls():
        if call.name == _REQUEST_CONFIRMATION_FUNCTION_CALL_NAME:
            continue
        messages.append({"type": "tool_call", "id": call.id, "name": call.name, "args": call.args})
    for response in event.get_function_responses():
        if response.name == _REQUEST_CONFIRMATION_FUNCTION_CALL_NAME:
            continue
        messages.append(
            {"type": "tool_result", "id": response.id, "name": response.name, "result": response.response}
        )
    return messages


def _confirmation_request(event) -> dict | None:
    """If this event is ADK's synthetic "please confirm" call, describe it.

    Returns a dict with the ORIGINAL tool call's name/args (what the user
    should actually be asked to approve), not adk_request_confirmation's
    own name/args — those are just the envelope.

    Simplification: only the first confirmation request in the event is
    handled if more than one is present (the model calling two
    confirmation-gated tools in the same turn) — not something this
    agent's single-step-per-turn instruction (APPCE-84) does in practice.
    """
    for call in event.get_function_calls():
        if call.name == _REQUEST_CONFIRMATION_FUNCTION_CALL_NAME:
            original = (call.args or {}).get("originalFunctionCall") or {}
            return {
                "type": "confirm_required",
                "id": call.id,
                "tool_name": original.get("name"),
                "args": original.get("args"),
            }
    return None


async def _similar_saved_facts(tenant_id: str, owner_uid: str, content) -> list[dict]:
    """Facts already saved that say (nearly) what a fact awaiting approval
    says, so the confirmation can warn about a duplicate (APPCE-111).

    Best effort, like the other side jobs of a turn: a failed lookup means
    no warning, never a failed confirmation.
    """
    if not isinstance(content, str):
        return []
    try:
        facts = await asyncio.to_thread(get_tenant_facts, tenant_id, owner_uid)
    except Exception as exc:
        log("WARNING", "best_effort_failed", what="similar facts", error=repr(exc))
        return []
    return find_similar_facts(content, facts)


async def _authenticate(websocket: WebSocket) -> str | None:
    """Read the first frame, {"type": "auth", "token": ...}, and verify it.

    Native browser WebSockets can't send custom headers, and a token in the
    URL ends up in every access log (uvicorn's, and Cloud Logging's on Cloud
    Run, where the app can't filter it), so the ID token travels in the first
    message instead — APPCE-67. It is verified the same way as on the REST
    endpoints (see api/deps.py), once, at connect time; a token that expires
    mid-conversation is only noticed when the socket reconnects, which the
    frontend does with its background-refreshed token (see APPCE-54).

    Returns the owner, or None after closing the socket with 1008.
    """
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), AUTH_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        await websocket.close(code=1008, reason="Authentication timed out")
        return None
    except WebSocketDisconnect:
        return None

    frame = None
    if len(raw) <= MAX_AUTH_FRAME_CHARS:
        try:
            frame = json.loads(raw)
        except ValueError:
            pass
    token = frame.get("token") if isinstance(frame, dict) and frame.get("type") == "auth" else None
    if not isinstance(token, str) or not token:
        await websocket.close(code=1008, reason="Authentication required")
        return None

    try:
        return await asyncio.to_thread(verify_token, token)
    except HTTPException as exc:
        await websocket.close(code=1008, reason=exc.detail)
        return None


# Thin, lazily-importing wrappers around api.runner.get_runner and
# api.session_memory.restore_session (APPCE-50): both modules pull in
# ADK's import chain, heavy enough to noticeably slow server startup if
# imported at module level, and only the chat socket below needs them —
# every other endpoint (e.g. /tenants, /usage, which the UI calls first)
# never touches them. Defined as real module-level names (not local
# imports inside chat()) so test/test_api_chat.py's
# `monkeypatch.setattr(api_main, "get_runner", ...)` keeps working — a
# local import would shadow the patched attribute instead of using it.
def get_runner(owner_uid: str, tenant_id: str):
    from api.runner import get_runner as _get_runner

    return _get_runner(owner_uid, tenant_id)


async def restore_session(*args, **kwargs):
    from api.session_memory import restore_session as _restore_session

    return await _restore_session(*args, **kwargs)


@app.websocket("/ws/chat/{tenant_id}")
async def chat(websocket: WebSocket, tenant_id: str):
    # Also deferred for startup speed (APPCE-50) — not part of the
    # monkeypatch surface above, so a plain local import is enough.
    from google.adk.agents.run_config import RunConfig
    from google.genai import types

    # The socket has to be accepted before it can be read from; nothing but
    # the auth frame is handled until _authenticate succeeds.
    await websocket.accept()
    owner_uid = await _authenticate(websocket)
    if owner_uid is None:
        return

    # Also confirms tenant_id is a project this user owns.
    try:
        await asyncio.to_thread(get_owned_tenant, tenant_id, owner_uid)
    except PermissionError:
        await websocket.close(code=1008, reason="Unknown project")
        return

    # Tells the UI it may start sending; messages sent while the session is
    # still being restored below simply wait their turn.
    await websocket.send_json({"type": "ready"})
    runner = get_runner(owner_uid, tenant_id)
    session_id = f"session_{tenant_id}"

    # After a restart the model has forgotten a conversation the UI still
    # shows; rebuild its memory from what was saved. Best effort — chatting
    # without restored memory beats not chatting because Firestore hiccuped.
    try:
        await restore_session(
            runner,
            owner_uid,
            session_id,
            lambda: load_recent_turns(tenant_id, owner_uid, get_settings(owner_uid)["history_turns"]),
        )
    except Exception as exc:
        log("WARNING", "chat_memory_restore_failed", error=repr(exc))

    # Set while a require_confirmation=True tool (APPCE-91) is waiting on
    # the user's approve/reject — the id of ADK's own synthetic
    # adk_request_confirmation call, not the original tool call's id.
    # pending_question carries the original question across the round trip,
    # so the eventual answer still gets saved correctly.
    pending_confirmation_id: str | None = None
    pending_question: str | None = None

    try:
        while True:
            data = await websocket.receive_json()
            if not isinstance(data, dict):
                await websocket.send_json({"type": "error", "message": "Malformed message."})
                continue

            # Clear chat: drop the server-side session too, not just the
            # UI's copy — otherwise the model keeps seeing (and billing
            # for) history the user believes is gone. auto_create_session
            # gives the next message a fresh one under the same id.
            if data.get("type") == "reset":
                await runner.session_service.delete_session(
                    app_name=runner.app_name, user_id=owner_uid, session_id=session_id
                )
                # ...and the saved copy, or the next cold start would bring
                # the conversation back from the dead.
                await _best_effort(clear_turns, tenant_id, owner_uid, what="clear saved chat history")
                pending_confirmation_id = None
                pending_question = None
                continue

            if data.get("type") == "confirm_response":
                if pending_confirmation_id is None:
                    await websocket.send_json(
                        {"type": "error", "message": "No confirmation is pending."}
                    )
                    continue
                message = types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            function_response=types.FunctionResponse(
                                id=pending_confirmation_id,
                                name=_REQUEST_CONFIRMATION_FUNCTION_CALL_NAME,
                                response={"confirmed": bool(data.get("confirmed"))},
                            )
                        )
                    ],
                )
                question = pending_question
                pending_confirmation_id = None
            else:
                if pending_confirmation_id is not None:
                    await websocket.send_json(
                        {"type": "error", "message": "Please approve or reject the pending action first."}
                    )
                    continue

                question = data.get("message")
                if not isinstance(question, str) or not question.strip():
                    await websocket.send_json({"type": "error", "message": "Message can't be empty."})
                    continue
                if len(question) > MAX_MESSAGE_CHARS:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": f"Message too long ({len(question)} characters, limit {MAX_MESSAGE_CHARS}).",
                        }
                    )
                    continue

                # The hard daily limit (APPCE-102) has to be decided before
                # any model call is made, so — unlike the other Firestore
                # calls here — this one is waited for. Counting and checking
                # are one transaction, so concurrent messages can't both
                # pass. Only the limit refuses a message: if Firestore itself
                # fails the counter is unavailable, and that is logged rather
                # than locking the user out (chat history and sessions
                # depend on the same Firestore anyway).
                try:
                    await asyncio.to_thread(record_message, owner_uid)
                except DailyLimitExceeded as exc:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": f"Daily message limit of {exc.limit} reached. It resets at midnight UTC.",
                        }
                    )
                    continue
                except Exception as exc:
                    log("WARNING", "usage_record_failed", error=repr(exc))
                # No "[Project: X]" prefix needed — the runner's Agent is
                # already scoped to this one tenant (see api/runner.py).
                message = types.Content(role="user", parts=[types.Part(text=question)])

            final_text = None
            confirmation = None

            try:
                async for event in _iterate_off_loop(
                    runner.run(
                        user_id=owner_uid,
                        session_id=session_id,
                        new_message=message,
                        run_config=RunConfig(max_llm_calls=MAX_LLM_CALLS_PER_TURN),
                    )
                ):
                    confirmation = confirmation or _confirmation_request(event)
                    if confirmation:
                        # Don't leak ADK's synthetic call into the Trace tab
                        # — it's not a real tool, and the actual tool call
                        # it wraps hasn't run yet.
                        continue
                    for msg in _event_to_messages(event):
                        await websocket.send_json(jsonable_encoder(msg))
                    if event.is_final_response() and event.content and event.content.parts:
                        final_text = event.content.parts[0].text
            except WebSocketDisconnect:
                raise
            except Exception as exc:
                # Includes ADK's LlmCallsLimitExceededError. Surface a
                # friendly error and keep the connection alive instead of
                # letting the socket die mid-question.
                log("ERROR", "agent_call_failed", error=repr(exc))
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": "Something went wrong while talking to the agent. Please try again.",
                    }
                )
                pending_question = None
                continue

            if confirmation:
                if confirmation["tool_name"] == "publish_fact":
                    confirmation["similar"] = await _similar_saved_facts(
                        tenant_id, owner_uid, (confirmation["args"] or {}).get("content")
                    )
                pending_confirmation_id = confirmation["id"]
                pending_question = question
                await websocket.send_json(confirmation)
                continue

            await websocket.send_json({"type": "final", "text": final_text or "(no response)"})

            # Only a real answer is worth saving; a turn that produced none
            # would restore as a question the model never answered.
            if final_text is not None and question is not None:
                await _best_effort(append_turn, tenant_id, owner_uid, question, final_text, what="save chat turn")
    except WebSocketDisconnect:
        pass


# Registered last on purpose: Starlette only falls through to a mount once
# no route above it has already matched the path, so this can never shadow
# an API route above. Only present in the production image (APPCE-56) —
# the Dockerfile bakes the React build in here; local dev keeps using the
# separate Vite dev server instead, so this directory won't exist there.
_FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend_dist"
if _FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=_FRONTEND_DIST, html=True), name="frontend")
