from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from google.genai import types

from api.deps import get_current_owner_uid
from api.runner import get_runner
from src.facts import get_tenant_facts
from src.tenants import list_tenants

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


def _event_to_messages(event) -> list[dict]:
    messages = []
    for call in event.get_function_calls():
        messages.append({"type": "tool_call", "name": call.name, "args": call.args})
    for response in event.get_function_responses():
        messages.append({"type": "tool_result", "name": response.name, "result": response.response})
    return messages


@app.websocket("/ws/chat/{tenant_id}")
async def chat(websocket: WebSocket, tenant_id: str, owner_uid: str):
    # TEMPORARY (APPCE-53 scaffolding, matches api/deps.py): owner_uid as
    # a query param, unverified. Replaced by real auth in APPCE-54.
    await websocket.accept()
    runner = get_runner(owner_uid)

    try:
        while True:
            data = await websocket.receive_json()
            question = data["message"]

            message = types.Content(role="user", parts=[types.Part(text=question)])
            final_text = "(no response)"

            for event in runner.run(
                user_id=owner_uid,
                session_id=f"session_{tenant_id}",
                new_message=message,
            ):
                for msg in _event_to_messages(event):
                    await websocket.send_json(jsonable_encoder(msg))
                if event.is_final_response() and event.content and event.content.parts:
                    final_text = event.content.parts[0].text

            await websocket.send_json({"type": "final", "text": final_text})
    except WebSocketDisconnect:
        pass
