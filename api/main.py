import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from api.deps import get_current_owner_uid, require_owner, verify_token
from api.internal_auth import verify_scheduler_token
from src.allowed_emails import OWNER_EMAILS, add_allowed_email, get_extra_allowed_emails, remove_allowed_email
from src.categories import ensure_categories_seeded
from src.chat_history import append_turn, clear_turns, load_recent_turns
from src.facts import get_tenant_facts
from src.github_client import validate_github_token
from src.github_connections import delete_github_connection, has_github_connection, save_github_token
from src.jira_client import validate_jira_credentials
from src.jira_connections import (
    delete_jira_connection,
    get_jira_base_url,
    has_jira_connection,
    save_jira_credentials,
)
from src.settings import BOUNDS, DEFAULTS, get_settings, reset_settings, save_settings
from src.tenants import add_tenant, delete_tenant, get_owned_tenant, list_tenants, rename_tenant
from src.usage import DAILY_MESSAGE_HARD_LIMIT, DailyLimitExceeded, get_today_count, next_reset_at, record_message

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

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Without this, a fresh deployment's Firestore has no config/categories
    # document until someone manually runs seed_data.py, and every
    # publish_fact call fails loudly until then (APPCE-93). No-op once the
    # document exists — never overwrites customized categories.
    ensure_categories_seeded()
    yield


app = FastAPI(title="Anamnesis API", lifespan=lifespan)

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
        print(f"{request.method} {request.url.path} -> {response.status_code} in {elapsed_ms:.0f} ms")
    return response


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


def poll_all_tenants() -> dict:
    # Deferred: pulls in the GitHub fact-extraction LLM call chain, which
    # only /internal/poll-github needs — same reasoning as the lazy
    # ADK/Pub-Sub imports elsewhere in this file (APPCE-50). A real
    # module-level name (not a local import inside the endpoint) so tests
    # can monkeypatch.setattr(api_main, "poll_all_tenants", ...).
    from src.github_polling import poll_all_tenants as _poll_all_tenants

    return _poll_all_tenants()


@app.post("/internal/poll-github")
def poll_github(_: None = Depends(verify_scheduler_token)) -> dict:
    return poll_all_tenants()


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
    tenant_id = add_tenant(body.name, owner_uid)
    return {"tenant_id": tenant_id}


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


@app.get("/tenants/{tenant_id}/facts")
def get_facts(tenant_id: str, owner_uid: str = Depends(get_current_owner_uid)) -> list[dict]:
    return get_tenant_facts(tenant_id, owner_uid)


# Lazily-importing wrappers (APPCE-50, same pattern as get_runner/
# restore_session below): src.pending_facts pulls in google-cloud-pubsub
# (via src.publisher, for the approve path), which only these three
# endpoints need — deferring it keeps it off every other request's
# startup cost. Real module-level names so
# test/test_api_pending_facts.py's monkeypatch.setattr(api_main, ...)
# still works.
def list_pending_facts(tenant_id: str, owner_uid: str) -> list[dict]:
    from src.pending_facts import list_pending_facts as _list_pending_facts

    return _list_pending_facts(tenant_id, owner_uid)


def approve_pending_fact(tenant_id: str, pending_fact_id: str, owner_uid: str) -> None:
    from src.pending_facts import approve_pending_fact as _approve_pending_fact

    return _approve_pending_fact(tenant_id, pending_fact_id, owner_uid)


def reject_pending_fact(tenant_id: str, pending_fact_id: str, owner_uid: str) -> None:
    from src.pending_facts import reject_pending_fact as _reject_pending_fact

    return _reject_pending_fact(tenant_id, pending_fact_id, owner_uid)


@app.get("/tenants/{tenant_id}/pending_facts")
def get_pending_facts(tenant_id: str, owner_uid: str = Depends(get_current_owner_uid)) -> list[dict]:
    try:
        return list_pending_facts(tenant_id, owner_uid)
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


@app.get("/usage")
def get_usage(owner_uid: str = Depends(get_current_owner_uid)) -> dict:
    return {
        "count": get_today_count(owner_uid),
        "threshold": get_settings(owner_uid)["daily_message_warning_threshold"],
        "limit": DAILY_MESSAGE_HARD_LIMIT,
        "resets_at": next_reset_at().isoformat(),
    }


# Who can sign in at all beyond the Terraform-configured owner(s) — only an
# owner can view/change this (require_owner), since anyone else granting
# access would defeat the allowlist (APPCE-94). A non-owner never even sees
# this section exists: the frontend just doesn't render it without a
# successful GET.
@app.get("/admin/allowed_emails")
def get_allowed_emails(owner_uid: str = Depends(require_owner)) -> dict:
    return {"owner_emails": sorted(OWNER_EMAILS), "extra_emails": sorted(get_extra_allowed_emails())}


class AllowedEmailCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(strict=True, min_length=1, max_length=320)


@app.post("/admin/allowed_emails")
def add_allowed_email_endpoint(body: AllowedEmailCreate, owner_uid: str = Depends(require_owner)) -> dict:
    try:
        add_allowed_email(body.email)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"extra_emails": sorted(get_extra_allowed_emails())}


@app.delete("/admin/allowed_emails/{email}")
def remove_allowed_email_endpoint(email: str, owner_uid: str = Depends(require_owner)) -> dict:
    remove_allowed_email(email)
    return {"extra_emails": sorted(get_extra_allowed_emails())}


class SettingsUpdate(BaseModel):
    # forbid: an unknown field is a client bug (or an attempt to write
    # arbitrary keys into the user's Firestore doc) — reject, don't ignore.
    # strict: "5" or true must not be quietly coerced into a valid int.
    model_config = ConfigDict(extra="forbid")

    history_turns: int = Field(strict=True, ge=BOUNDS["history_turns"][0], le=BOUNDS["history_turns"][1])
    daily_message_warning_threshold: int = Field(
        strict=True,
        ge=BOUNDS["daily_message_warning_threshold"][0],
        le=BOUNDS["daily_message_warning_threshold"][1],
    )


def _settings_response(settings: dict) -> dict:
    # The bounds and defaults ride along so the UI can render min/max and
    # know what "reset" means from the one source of truth instead of
    # hardcoding its own copies.
    return {
        **settings,
        "limits": {name: {"min": low, "max": high} for name, (low, high) in BOUNDS.items()},
        "defaults": dict(DEFAULTS),
    }


@app.get("/settings")
def read_settings(owner_uid: str = Depends(get_current_owner_uid)) -> dict:
    return _settings_response(get_settings(owner_uid))


@app.put("/settings")
def update_settings(body: SettingsUpdate, owner_uid: str = Depends(get_current_owner_uid)) -> dict:
    # owner_uid comes from the verified token, never the body — a user can
    # only ever write their own settings.
    return _settings_response(save_settings(owner_uid, body.model_dump()))


@app.delete("/settings")
def delete_settings(owner_uid: str = Depends(get_current_owner_uid)) -> dict:
    return _settings_response(reset_settings(owner_uid))


class GithubConnectionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(strict=True, min_length=1, max_length=255)


@app.get("/github/connection")
def read_github_connection(owner_uid: str = Depends(get_current_owner_uid)) -> dict:
    return {"connected": has_github_connection(owner_uid)}


@app.put("/github/connection")
def update_github_connection(
    body: GithubConnectionUpdate, owner_uid: str = Depends(get_current_owner_uid)
) -> dict:
    # Validated before it ever reaches Firestore — an invalid/wrong-kind
    # token must not get encrypted and stored, only to fail on first use.
    try:
        validate_github_token(body.token)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    save_github_token(owner_uid, body.token)
    return {"connected": True}


@app.delete("/github/connection")
def remove_github_connection(owner_uid: str = Depends(get_current_owner_uid)) -> dict:
    delete_github_connection(owner_uid)
    return {"connected": False}


class JiraConnectionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(strict=True, min_length=1, max_length=255)
    token: str = Field(strict=True, min_length=1, max_length=255)
    base_url: str = Field(strict=True, min_length=1, max_length=255)


@app.get("/jira/connection")
def read_jira_connection(owner_uid: str = Depends(get_current_owner_uid)) -> dict:
    connected = has_jira_connection(owner_uid)
    # The workspace address (not the token) lets the UI link a project's
    # Jira key; there is nothing to link when nothing is connected.
    return {"connected": connected, "base_url": get_jira_base_url(owner_uid) if connected else None}


@app.put("/jira/connection")
def update_jira_connection(body: JiraConnectionUpdate, owner_uid: str = Depends(get_current_owner_uid)) -> dict:
    # Validated before it ever reaches Firestore — bad credentials must
    # not get encrypted and stored, only to fail on first use.
    try:
        validate_jira_credentials(body.email, body.token, body.base_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    save_jira_credentials(owner_uid, body.email, body.token, body.base_url)
    return {"connected": True}


@app.delete("/jira/connection")
def remove_jira_connection(owner_uid: str = Depends(get_current_owner_uid)) -> dict:
    delete_jira_connection(owner_uid)
    return {"connected": False}


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
        print(f"Couldn't {what}: {exc!r}")


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
        print(f"Couldn't restore chat memory: {exc!r}")

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
                    print(f"Couldn't record message usage: {exc!r}")
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
                print(f"Agent call failed: {exc!r}")
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": "Something went wrong while talking to the agent. Please try again.",
                    }
                )
                pending_question = None
                continue

            if confirmation:
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
