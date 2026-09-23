import asyncio
import json
import os
import time

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from google.adk.agents.run_config import RunConfig
from google.genai import types
from pydantic import BaseModel, ConfigDict, Field

from api.deps import get_current_owner_uid, verify_token
from api.runner import get_runner
from api.session_memory import format_user_message, restore_session
from src.chat_history import append_turn, clear_turns, load_recent_turns
from src.facts import get_tenant_facts
from src.github_client import validate_github_token
from src.github_connections import delete_github_connection, has_github_connection, save_github_token
from src.pending_facts import approve_pending_fact, list_pending_facts, reject_pending_fact
from src.settings import BOUNDS, DEFAULTS, get_settings, reset_settings, save_settings
from src.tenants import get_owned_tenant, list_tenants
from src.usage import get_today_count, record_message

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

# Local dev only — the Vite dev server's origin. APPCE-56 (Terraform/
# deploy) revisits this once the frontend has a real deployed origin.
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


@app.get("/tenants")
def get_tenants(owner_uid: str = Depends(get_current_owner_uid)) -> list[dict]:
    return list_tenants(owner_uid)


@app.get("/tenants/{tenant_id}/facts")
def get_facts(tenant_id: str, owner_uid: str = Depends(get_current_owner_uid)) -> list[dict]:
    return get_tenant_facts(tenant_id, owner_uid)


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
    }


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


def _event_to_messages(event) -> list[dict]:
    # The id pairs a result with its call for the UI's Trace tab — matching
    # by tool name alone breaks as soon as the model calls one tool twice.
    messages = []
    for call in event.get_function_calls():
        messages.append({"type": "tool_call", "id": call.id, "name": call.name, "args": call.args})
    for response in event.get_function_responses():
        messages.append(
            {"type": "tool_result", "id": response.id, "name": response.name, "result": response.response}
        )
    return messages


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


@app.websocket("/ws/chat/{tenant_id}")
async def chat(websocket: WebSocket, tenant_id: str):
    # The socket has to be accepted before it can be read from; nothing but
    # the auth frame is handled until _authenticate succeeds.
    await websocket.accept()
    owner_uid = await _authenticate(websocket)
    if owner_uid is None:
        return

    # Also confirms tenant_id is a project this user owns — until now it
    # was only ever used to name the session — and gives us the display
    # name the agent needs (below).
    try:
        tenant_name = (await asyncio.to_thread(get_owned_tenant, tenant_id, owner_uid))["name"]
    except PermissionError:
        await websocket.close(code=1008, reason="Unknown project")
        return

    # Tells the UI it may start sending; messages sent while the session is
    # still being restored below simply wait their turn.
    await websocket.send_json({"type": "ready"})
    runner = get_runner(owner_uid)
    session_id = f"session_{tenant_id}"

    # After a restart the model has forgotten a conversation the UI still
    # shows; rebuild its memory from what was saved. Best effort — chatting
    # without restored memory beats not chatting because Firestore hiccuped.
    try:
        await restore_session(
            runner,
            owner_uid,
            session_id,
            tenant_name,
            lambda: load_recent_turns(tenant_id, owner_uid, get_settings(owner_uid)["history_turns"]),
        )
    except Exception as exc:
        print(f"Couldn't restore chat memory: {exc!r}")

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

            # The usage counter is a soft UI warning, so the model call
            # doesn't wait for it: it runs alongside the turn and is
            # awaited once the turn is done.
            usage_task = asyncio.create_task(
                _best_effort(record_message, owner_uid, what="record message usage")
            )

            message = types.Content(
                role="user", parts=[types.Part(text=format_user_message(tenant_name, question))]
            )
            final_text = None

            try:
                async for event in _iterate_off_loop(
                    runner.run(
                        user_id=owner_uid,
                        session_id=session_id,
                        new_message=message,
                        run_config=RunConfig(max_llm_calls=MAX_LLM_CALLS_PER_TURN),
                    )
                ):
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
                await usage_task
                continue

            await websocket.send_json({"type": "final", "text": final_text or "(no response)"})
            await usage_task

            # Only a real answer is worth saving; a turn that produced none
            # would restore as a question the model never answered.
            if final_text is not None:
                await _best_effort(append_turn, tenant_id, owner_uid, question, final_text, what="save chat turn")
    except WebSocketDisconnect:
        pass
