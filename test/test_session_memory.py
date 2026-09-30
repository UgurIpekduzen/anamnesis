"""Tests for restoring saved chat turns into an ADK session on cold start."""

import asyncio
from types import SimpleNamespace

from google.adk.errors.already_exists_error import AlreadyExistsError
from google.adk.sessions import InMemorySessionService

from api.session_memory import restore_session

OWNER = "test@example.com"
SESSION = "session_some_tenant"
TURNS = [
    {"question": "first question", "answer": "first answer"},
    {"question": "second question", "answer": "second answer"},
]


def _runner(service=None):
    return SimpleNamespace(
        session_service=service or InMemorySessionService(),
        app_name="anamnesis",
        agent=SimpleNamespace(name="root_agent"),
    )


def _events(runner):
    session = asyncio.run(
        runner.session_service.get_session(app_name="anamnesis", user_id=OWNER, session_id=SESSION)
    )
    return session.events if session else None


def _restore(runner, load_turns):
    return asyncio.run(restore_session(runner, OWNER, SESSION, load_turns))


def test_saved_turns_become_alternating_user_and_agent_events_in_order():
    """Saved turns are restored as alternating user/agent events, in the same order and with the same text."""
    runner = _runner()

    assert _restore(runner, lambda: TURNS) is True

    events = _events(runner)
    assert [(e.author, e.content.role) for e in events] == [
        ("user", "user"),
        ("root_agent", "model"),
        ("user", "user"),
        ("root_agent", "model"),
    ]
    assert [e.content.parts[0].text for e in events] == [
        "first question",
        "first answer",
        "second question",
        "second answer",
    ]


def test_a_question_and_its_answer_share_an_invocation():
    """Each restored question and its answer share one invocation id, and different turns get different invocation ids."""
    runner = _runner()
    _restore(runner, lambda: TURNS)

    first, second, third, fourth = _events(runner)
    assert first.invocation_id == second.invocation_id
    assert third.invocation_id == fourth.invocation_id
    assert first.invocation_id != third.invocation_id


def test_nothing_saved_means_no_session_is_created():
    """When there are no saved turns to load, restore_session returns False and no session is created."""
    runner = _runner()

    assert _restore(runner, lambda: []) is False

    assert _events(runner) is None


def test_a_live_session_is_never_overwritten_and_saved_turns_are_not_even_read():
    """restore_session leaves an already-existing session untouched and never even calls the loader for saved turns."""
    runner = _runner()
    _restore(runner, lambda: TURNS)
    before = len(_events(runner))
    reads = []

    def load():
        """Record that it was called, and return the saved turns."""
        reads.append(1)
        return TURNS

    assert _restore(runner, load) is False

    assert len(_events(runner)) == before
    assert reads == []  # a warm session costs no Firestore reads


def test_losing_the_race_to_another_connection_is_not_an_error():
    """When another connection creates the session first, restore_session treats the resulting AlreadyExistsError as a normal loss, not a failure."""

    class RacyService(InMemorySessionService):
        """A session service whose create_session always loses the race to an existing session."""

        async def create_session(self, **kwargs):
            """Simulate another connection having already created this session."""
            raise AlreadyExistsError("someone else got there first")

    assert _restore(_runner(RacyService()), lambda: TURNS) is False
