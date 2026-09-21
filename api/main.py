import os

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from google.adk.agents.run_config import RunConfig
from google.genai import types
from pydantic import BaseModel, ConfigDict, Field

from api.deps import get_current_owner_uid, verify_token
from api.runner import get_runner
from src.facts import get_tenant_facts
from src.settings import BOUNDS, DEFAULTS, get_settings, reset_settings, save_settings
from src.tenants import list_tenants
from src.usage import get_today_count, record_message

# Token-cost guards (see APPCE-59). A message stays in the session history
# and is resent on every model call of the following turns, so an
# unbounded one is the most expensive input a user can send. A normal
# turn takes 3-4 model calls; ADK's own default cap is 500.
MAX_MESSAGE_CHARS = int(os.environ.get("MAX_MESSAGE_CHARS", 4000))
MAX_LLM_CALLS_PER_TURN = int(os.environ.get("MAX_LLM_CALLS_PER_TURN", 10))

app = FastAPI(title="Anamnesis API")

# Local dev only — the Vite dev server's origin. APPCE-56 (Terraform/
# deploy) revisits this once the frontend has a real deployed origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/tenants")
def get_tenants(owner_uid: str = Depends(get_current_owner_uid)) -> list[dict]:
    return list_tenants(owner_uid)


@app.get("/tenants/{tenant_id}/facts")
def get_facts(tenant_id: str, owner_uid: str = Depends(get_current_owner_uid)) -> list[dict]:
    return get_tenant_facts(tenant_id, owner_uid)


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


def _event_to_messages(event) -> list[dict]:
    messages = []
    for call in event.get_function_calls():
        messages.append({"type": "tool_call", "name": call.name, "args": call.args})
    for response in event.get_function_responses():
        messages.append({"type": "tool_result", "name": response.name, "result": response.response})
    return messages


@app.websocket("/ws/chat/{tenant_id}")
async def chat(websocket: WebSocket, tenant_id: str, token: str):
    # Native browser WebSockets can't send custom headers, so the ID
    # token travels as a query param instead of Authorization — verified
    # the same way as the REST endpoints (see api/deps.py). Checked once
    # at connect time; a token that expires mid-conversation closes the
    # socket on its next send, and the frontend reconnects with its
    # background-refreshed token (see APPCE-54).
    try:
        owner_uid = verify_token(token)
    except HTTPException as exc:
        await websocket.close(code=1008, reason=exc.detail)
        return

    await websocket.accept()
    runner = get_runner(owner_uid)
    session_id = f"session_{tenant_id}"

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

            record_message(owner_uid)

            message = types.Content(role="user", parts=[types.Part(text=question)])
            final_text = "(no response)"

            try:
                for event in runner.run(
                    user_id=owner_uid,
                    session_id=session_id,
                    new_message=message,
                    run_config=RunConfig(max_llm_calls=MAX_LLM_CALLS_PER_TURN),
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
                continue

            await websocket.send_json({"type": "final", "text": final_text})
    except WebSocketDisconnect:
        pass
