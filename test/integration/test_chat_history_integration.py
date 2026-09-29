"""Integration tests for per-project chat history storage and retention
against a real Firestore emulator."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from src.projects.chat_history import RETENTION_DAYS, append_turn, clear_turns, load_recent_turns
from src.core.firestore_client import get_client
from src.projects.tenants import CHAT_TURNS_COLLECTION, add_tenant, delete_tenant

OWNER = "test-owner@example.com"
STRANGER = "someone-else@example.com"


def _new_tenant():
    return add_tenant(f"Integration Test Tenant {uuid.uuid4().hex[:8]}", OWNER)


@pytest.fixture
def tenant_id():
    """Create a real tenant owned by OWNER and yield its id, deleting the
    tenant afterwards (tolerating a test that already deleted it)."""
    tenant_id = _new_tenant()
    yield tenant_id
    try:
        delete_tenant(tenant_id, OWNER)
    except PermissionError:
        pass  # a test already deleted it


def _stored_turn_count(tenant_id):
    ref = get_client().collection("tenants").document(tenant_id).collection(CHAT_TURNS_COLLECTION)
    return len(list(ref.stream()))


def test_turns_come_back_oldest_first_with_their_text(tenant_id):
    """load_recent_turns returns appended turns oldest-first, each with its
    question, answer, and a real created_at timestamp."""
    append_turn(tenant_id, OWNER, "first question", "first answer")
    append_turn(tenant_id, OWNER, "second question", "second answer")

    turns = load_recent_turns(tenant_id, OWNER, limit=10)

    assert [(t["question"], t["answer"]) for t in turns] == [
        ("first question", "first answer"),
        ("second question", "second answer"),
    ]
    assert all(isinstance(t["created_at"], datetime) for t in turns)


def test_the_limit_keeps_the_most_recent_turns_in_order(tenant_id):
    """load_recent_turns with a limit smaller than the stored history returns
    only the most recent turns, still oldest-first."""
    for n in range(1, 5):
        append_turn(tenant_id, OWNER, f"q{n}", f"a{n}")

    turns = load_recent_turns(tenant_id, OWNER, limit=2)

    assert [t["question"] for t in turns] == ["q3", "q4"]


def test_a_zero_limit_returns_nothing(tenant_id):
    """load_recent_turns with limit=0 returns an empty list even though a
    turn exists."""
    append_turn(tenant_id, OWNER, "q", "a")
    assert load_recent_turns(tenant_id, OWNER, limit=0) == []


def test_each_turn_is_stamped_to_expire_after_the_retention_period(tenant_id):
    """append_turn stores an expire_at timestamp RETENTION_DAYS after the
    turn is created, for Firestore's TTL sweep."""
    before = datetime.now(timezone.utc)
    append_turn(tenant_id, OWNER, "q", "a")

    ref = get_client().collection("tenants").document(tenant_id).collection(CHAT_TURNS_COLLECTION)
    stored = next(iter(ref.stream())).to_dict()

    expected = before + timedelta(days=RETENTION_DAYS)
    assert abs((stored["expire_at"] - expected).total_seconds()) < 60


def test_an_expired_turn_is_not_returned_even_if_the_ttl_sweep_has_not_run(tenant_id):
    """load_recent_turns filters out a turn whose expire_at is already in the
    past, even though Firestore's TTL sweep hasn't deleted it yet."""
    append_turn(tenant_id, OWNER, "still live", "yes")
    ref = get_client().collection("tenants").document(tenant_id).collection(CHAT_TURNS_COLLECTION)
    ref.add(
        {
            "question": "long gone",
            "answer": "yes",
            "created_at": datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS + 5),
            "expire_at": datetime.now(timezone.utc) - timedelta(days=5),
        }
    )

    assert [t["question"] for t in load_recent_turns(tenant_id, OWNER, limit=10)] == ["still live"]


def test_clearing_removes_the_saved_turns(tenant_id):
    """clear_turns deletes a project's saved turns so load_recent_turns
    returns nothing afterwards."""
    append_turn(tenant_id, OWNER, "q", "a")
    clear_turns(tenant_id, OWNER)
    assert load_recent_turns(tenant_id, OWNER, limit=10) == []


def test_clearing_one_project_leaves_another_projects_turns_alone(tenant_id):
    """clear_turns on one project's history doesn't remove another project's
    turns."""
    other = _new_tenant()
    try:
        append_turn(tenant_id, OWNER, "mine", "a")
        append_turn(other, OWNER, "theirs", "a")

        clear_turns(tenant_id, OWNER)

        assert [t["question"] for t in load_recent_turns(other, OWNER, limit=10)] == ["theirs"]
    finally:
        delete_tenant(other, OWNER)


@pytest.mark.parametrize(
    "operation",
    [
        lambda t: append_turn(t, STRANGER, "q", "a"),
        lambda t: load_recent_turns(t, STRANGER, limit=10),
        lambda t: clear_turns(t, STRANGER),
    ],
    ids=["append", "load", "clear"],
)
def test_someone_elses_project_is_off_limits(tenant_id, operation):
    """append_turn, load_recent_turns, and clear_turns each raise
    PermissionError for a caller who isn't the project's owner, and leave the
    owner's existing turns untouched."""
    append_turn(tenant_id, OWNER, "private", "a")

    with pytest.raises(PermissionError):
        operation(tenant_id)

    # ...and the owner's data was neither read out nor touched.
    assert [t["question"] for t in load_recent_turns(tenant_id, OWNER, limit=10)] == ["private"]


def test_deleting_a_project_deletes_its_saved_turns(tenant_id):
    """delete_tenant also deletes the project's saved chat turns."""
    append_turn(tenant_id, OWNER, "q", "a")
    assert _stored_turn_count(tenant_id) == 1

    delete_tenant(tenant_id, OWNER)

    assert _stored_turn_count(tenant_id) == 0
