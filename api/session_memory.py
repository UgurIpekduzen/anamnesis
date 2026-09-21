import asyncio
import uuid
from collections.abc import Callable

from google.adk.errors.already_exists_error import AlreadyExistsError
from google.adk.events.event import Event
from google.genai import types


def format_user_message(tenant_name: str, question: str) -> str:
    """What the model actually sees for a user turn.

    The agent has no other way to know which project the UI has selected —
    without this prefix it just asks "which project?" (the convention the
    Streamlit UI used in app/chat.py). Shared by the live path and by
    restore_session so a restored history reads exactly like a live one.
    """
    return f"[Project: {tenant_name}] {question}"


async def restore_session(
    runner, owner_uid: str, session_id: str, tenant_name: str, load_turns: Callable[[], list[dict]]
) -> bool:
    """Rebuild the model's memory of a conversation from saved turns.

    The ADK session lives in this process's memory, so after a restart (a
    deploy, Cloud Run scaling to zero) the model would have forgotten a
    conversation the UI still shows. This seeds a fresh session from the
    turns saved in Firestore (src/chat_history.py) — see APPCE-60.

    Only the question/answer text is restored, not the tool calls and
    results of the original turns; the model sees what was said and can call
    a tool again if it needs the data.

    load_turns is only called when there is actually a session to rebuild,
    so a connection to a warm session costs no Firestore reads.

    Returns True if it seeded a session, False if there was nothing to do:
    a session already in memory (never overwrite a live one), no saved
    turns, or another connection restoring it first.
    """
    service = runner.session_service
    if await service.get_session(app_name=runner.app_name, user_id=owner_uid, session_id=session_id):
        return False

    # Blocking Firestore reads — off the event loop (APPCE-62).
    turns = await asyncio.to_thread(load_turns)
    if not turns:
        return False

    try:
        session = await service.create_session(
            app_name=runner.app_name, user_id=owner_uid, session_id=session_id
        )
    except AlreadyExistsError:
        return False

    # ADK treats an event authored by anything other than "user" or the
    # running agent as another agent's speech and rewrites it — the model's
    # own past answers must carry this agent's name to read as its own.
    agent_name = runner.agent.name
    for turn in turns:
        invocation_id = f"restored-{uuid.uuid4()}"
        await service.append_event(
            session,
            Event(
                invocation_id=invocation_id,
                author="user",
                content=types.Content(
                    role="user",
                    parts=[types.Part(text=format_user_message(tenant_name, turn["question"]))],
                ),
            ),
        )
        await service.append_event(
            session,
            Event(
                invocation_id=invocation_id,
                author=agent_name,
                content=types.Content(role="model", parts=[types.Part(text=turn["answer"])]),
            ),
        )
    return True
