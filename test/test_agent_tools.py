"""Tests for the ADK agent's tool wiring, wrappers, and instruction text."""

import pytest

import agent.agent as agent_module
from src.facts.categories import InvalidCategory


@pytest.fixture(autouse=True)
def _suggested_categories(monkeypatch):
    # The instruction reads the user's list from Firestore; no test here needs it.
    monkeypatch.setattr(
        agent_module, "get_categories", lambda owner_uid: ["architecture", "decision", "risk"]
    )


def _instruction(built_agent):
    # ADK calls the instruction function every turn, with the turn's context.
    return built_agent.instruction(None)


def _tool_name(t):
    # Plain functions expose __name__; tools wrapped in
    # FunctionTool(..., require_confirmation=True) expose .name
    # instead and have no __name__ at all.
    return getattr(t, "name", None) or t.__name__


def _tool_by_name(tools, name):
    return next(t for t in tools if _tool_name(t) == name)


def _callable(t):
    # A FunctionTool isn't directly callable like a plain function — .func
    # is the actual wrapper with owner_uid/tenant_id already bound, which
    # is what these tests care about (the confirmation gate itself is
    # tested separately, in test_api_chat.py).
    return t.func if hasattr(t, "func") else t


def test_the_agents_facts_tool_is_capped_and_says_so():
    """The get_tenant_facts tool binds tenant_id/owner_uid and caps the result at MAX_FACTS_PER_TOOL_CALL, and its docstring says so."""
    tool_agent = agent_module.build_agent("test@example.com", "some_tenant")
    tool = _tool_by_name(tool_agent.tools, "get_tenant_facts")

    # The wrapper looks get_tenant_facts up at call time, so patching after
    # build_agent leaves the docstring copy (which needs the real one) alone.
    seen = {}

    def fake_get_tenant_facts(tenant_id, owner_uid, limit=None):
        """Record the arguments the tool wrapper was called with and return no facts."""
        seen.update(tenant_id=tenant_id, owner_uid=owner_uid, limit=limit)
        return []

    original = agent_module.get_tenant_facts
    agent_module.get_tenant_facts = fake_get_tenant_facts
    try:
        # No arguments — tenant_id and owner_uid are both bound at build
        # time now, neither is part of the model-facing signature.
        tool()
    finally:
        agent_module.get_tenant_facts = original

    assert seen == {
        "tenant_id": "some_tenant",
        "owner_uid": "test@example.com",
        "limit": agent_module.MAX_FACTS_PER_TOOL_CALL,
    }
    # Without this the model would read a truncated list as the whole history.
    assert "most recent" in tool.__doc__


def test_get_github_status_has_owner_uid_and_tenant_id_bound():
    """The get_github_status tool calls through with owner_uid and tenant_id already bound, taking no arguments from the model."""
    tool_agent = agent_module.build_agent("test@example.com", "some_tenant")
    tool = _tool_by_name(tool_agent.tools, "get_github_status")

    seen = {}

    def fake_get_github_status(owner_uid, tenant_id):
        """Record the arguments the tool wrapper was called with and return an empty status."""
        seen.update(owner_uid=owner_uid, tenant_id=tenant_id)
        return {"pull_requests": [], "issues": []}

    original = agent_module.get_github_status
    agent_module.get_github_status = fake_get_github_status
    try:
        tool()  # no arguments — both are bound at build time
    finally:
        agent_module.get_github_status = original

    assert seen == {"owner_uid": "test@example.com", "tenant_id": "some_tenant"}


def test_get_jira_status_resolves_the_project_key_and_the_users_own_credentials():
    """The get_jira_status tool looks up the tenant's linked project key and the calling user's own Jira credentials before querying."""
    tool_agent = agent_module.build_agent("test@example.com", "some_tenant")
    tool = _tool_by_name(tool_agent.tools, "get_jira_status")

    calls = []

    original_owned = agent_module.get_owned_tenant
    original_creds = agent_module.get_jira_credentials
    original_status = agent_module.get_jira_status
    agent_module.get_owned_tenant = lambda tenant_id, owner_uid: {"jira_project_key": "APPCE"}
    agent_module.get_jira_credentials = lambda owner_uid: {
        "email": "user@example.com",
        "token": "secret-token",
        "base_url": "https://example.atlassian.net",
    }
    agent_module.get_jira_status = lambda project_key, email, token, base_url: (
        calls.append((project_key, email, token, base_url)) or [{"key": "APPCE-1"}]
    )
    try:
        result = tool()
    finally:
        agent_module.get_owned_tenant = original_owned
        agent_module.get_jira_credentials = original_creds
        agent_module.get_jira_status = original_status

    assert calls == [("APPCE", "user@example.com", "secret-token", "https://example.atlassian.net")]
    assert result == [{"key": "APPCE-1"}]


def test_get_jira_status_returns_an_error_result_when_the_tenant_has_no_linked_project():
    """get_jira_status returns an {"error": ...} result, not a raised exception, when the tenant has no linked Jira project key."""
    # Not a raised exception: ADK doesn't turn an uncaught one into a tool
    # result the model can read, it crashes the whole turn instead — this
    # must come back as a normal {"error": ...} result.
    tool_agent = agent_module.build_agent("test@example.com", "some_tenant")
    tool = _tool_by_name(tool_agent.tools, "get_jira_status")

    original_owned = agent_module.get_owned_tenant
    agent_module.get_owned_tenant = lambda tenant_id, owner_uid: {}
    try:
        result = tool()
    finally:
        agent_module.get_owned_tenant = original_owned

    assert result == {"error": "This project has no linked Jira project key."}


def test_get_jira_status_reports_a_saved_token_the_current_key_cannot_read(monkeypatch):
    """get_jira_status turns an UnreadableToken error into a "reconnect it in Settings" result instead of crashing the turn."""
    # An uncaught error here would crash the whole turn; a lost
    # encryption key must reach the user as "reconnect it" instead.
    from src.core.token_encryption import UnreadableToken

    def unreadable(owner_uid):
        """Simulate a saved Jira token that the current encryption key can't decrypt."""
        raise UnreadableToken("The saved token can't be decrypted. Reconnect it in Settings.")

    monkeypatch.setattr(
        agent_module, "get_owned_tenant", lambda tenant_id, owner_uid: {"jira_project_key": "APPCE"}
    )
    monkeypatch.setattr(agent_module, "get_jira_credentials", unreadable)
    tool = _tool_by_name(
        agent_module.build_agent("test@example.com", "some_tenant").tools, "get_jira_status"
    )

    assert tool() == {"error": "The saved token can't be decrypted. Reconnect it in Settings."}


def test_get_jira_status_returns_an_error_result_when_the_user_has_no_jira_connection():
    """get_jira_status returns an {"error": ...} result when the calling user has no Jira credentials connected."""
    tool_agent = agent_module.build_agent("test@example.com", "some_tenant")
    tool = _tool_by_name(tool_agent.tools, "get_jira_status")

    original_owned = agent_module.get_owned_tenant
    original_creds = agent_module.get_jira_credentials
    agent_module.get_owned_tenant = lambda tenant_id, owner_uid: {"jira_project_key": "APPCE"}
    agent_module.get_jira_credentials = lambda owner_uid: None
    try:
        result = tool()
    finally:
        agent_module.get_owned_tenant = original_owned
        agent_module.get_jira_credentials = original_creds

    assert result == {"error": "No Jira account connected. Connect one in Settings."}


def test_get_github_status_returns_an_error_result_instead_of_raising():
    """get_github_status turns a raised ValueError into an {"error": ...} result instead of letting it propagate."""
    tool_agent = agent_module.build_agent("test@example.com", "some_tenant")
    tool = _tool_by_name(tool_agent.tools, "get_github_status")

    original = agent_module.get_github_status
    agent_module.get_github_status = lambda owner_uid, tenant_id: (_ for _ in ()).throw(
        ValueError("Tenant 'some_tenant' has no GitHub repo attached.")
    )
    try:
        result = tool()
    finally:
        agent_module.get_github_status = original

    assert result == {"error": "Tenant 'some_tenant' has no GitHub repo attached."}


def test_tenant_lifecycle_tools_are_not_exposed_to_the_model():
    """The agent's tool list has no list_tenants/add_tenant/rename_tenant/delete_tenant tools; project lifecycle is UI-only."""
    tool_agent = agent_module.build_agent("test@example.com", "some_tenant")
    tool_names = {_tool_name(t) for t in tool_agent.tools}

    # Creating/renaming/deleting projects is UI-only now (see
    # api/routers/tenants.py) — the agent has nothing to scope those to.
    assert tool_names.isdisjoint({"list_tenants", "add_tenant", "rename_tenant", "delete_tenant"})


def test_the_agent_cannot_link_a_project_to_a_repo_or_a_jira_project_itself():
    """The agent's tool list has no set_github_repo/set_jira_project_key/set_git_repo_path tools; linking is done by the user."""
    tool_agent = agent_module.build_agent("test@example.com", "some_tenant")
    tool_names = {_tool_name(t) for t in tool_agent.tools}

    # Which repo is polled and which Jira project is queried is decided by the
    # user pressing a button, not by a model that reads text other
    # people wrote. git_repo_path went with them: nothing else sets it.
    assert tool_names.isdisjoint({"set_github_repo", "set_jira_project_key", "set_git_repo_path"})


def test_the_only_tool_that_writes_is_publish_fact_and_it_asks_first():
    """Only publish_fact is wrapped with confirmation required; every other tool is a plain, read-or-propose-only function."""
    tool_agent = agent_module.build_agent("test@example.com", "some_tenant")

    # A FunctionTool is what require_confirmation=True wraps a tool in;
    # the plain functions read or only propose.
    confirming = {_tool_name(t) for t in tool_agent.tools if hasattr(t, "func")}
    plain = {_tool_name(t) for t in tool_agent.tools if not hasattr(t, "func")}

    assert confirming == {"publish_fact"}
    assert plain == {
        "get_tenant_facts",
        "get_github_status",
        "get_jira_status",
        "get_jira_recently_done",
        "get_github_history",
        "get_pending_facts",
        "propose_link",
        "propose_fact_update",
        "propose_fact_delete",
    }


def _propose_link(monkeypatch, kind, value, current=None):
    def no_database(*args, **kwargs):
        """Fail the test if propose_link tries to touch Firestore."""
        raise AssertionError("a proposal must not write anything")

    monkeypatch.setattr("src.projects.tenants.get_client", no_database)
    monkeypatch.setattr(
        agent_module, "get_owned_tenant", lambda tenant_id, owner_uid: {kind: current}
    )
    tool = _tool_by_name(
        agent_module.build_agent("test@example.com", "some_tenant").tools, "propose_link"
    )
    return tool(kind, value)


def test_propose_link_returns_a_proposal_and_writes_nothing(monkeypatch):
    """propose_link returns a proposal describing the current and new value, without writing to Firestore."""
    result = _propose_link(monkeypatch, "github_repo", "owner/repo", current="old/repo")

    assert result == {
        "proposal": "link",
        "kind": "github_repo",
        "value": "owner/repo",
        "current": "old/repo",
    }


def test_propose_link_accepts_a_jira_key(monkeypatch):
    """propose_link also accepts a jira_project_key proposal, with no prior value."""
    result = _propose_link(monkeypatch, "jira_project_key", "APPCE")

    assert result == {
        "proposal": "link",
        "kind": "jira_project_key",
        "value": "APPCE",
        "current": None,
    }


def test_propose_link_turns_an_invalid_value_into_an_error_result(monkeypatch):
    """propose_link returns an error result for a malformed repo, a malformed Jira key, or an unknown link kind."""
    for kind, value in [
        ("github_repo", "not a repo"),
        ("jira_project_key", 'X" OR project != "'),
        ("other", "x"),
    ]:
        assert "error" in _propose_link(monkeypatch, kind, value)


def test_the_agent_says_a_link_needs_the_users_button_press():
    """The agent's instruction mentions propose_link and tells the model the user must press a button, naming no removed set_ tool."""
    instruction = _instruction(agent_module.build_agent("test@example.com", "some_tenant"))

    assert "propose_link" in instruction
    assert "press" in instruction
    assert "set_" not in instruction  # it must not name a tool it no longer has


FACT = {"fact_id": "f1", "content": "Uses PostgreSQL", "category": "architecture"}


def _fact_tool(monkeypatch, name, fact=FACT):
    def no_database(*args, **kwargs):
        """Fail the test if a propose_fact_* tool tries to touch Firestore."""
        raise AssertionError("a proposal must not write anything")

    monkeypatch.setattr("src.facts.facts.get_client", no_database)

    def fake_get_fact(tenant_id, fact_id, owner_uid):
        """Return the given fact if its id matches, else raise as a real lookup would for an unknown id."""
        if fact is None or fact_id != fact["fact_id"]:
            raise LookupError(f"No fact '{fact_id}' in this project.")
        return fact

    monkeypatch.setattr(agent_module, "get_fact", fake_get_fact)
    monkeypatch.setattr(
        agent_module,
        "validate_category_for",
        lambda owner_uid, c: None if c in {"bug", "decision"} else _bad(c),
    )
    return _tool_by_name(agent_module.build_agent("test@example.com", "some_tenant").tools, name)


def _bad(category):
    raise ValueError(f"Invalid category '{category}'")


def test_propose_fact_update_shows_the_old_and_the_new_and_keeps_what_was_not_changed(monkeypatch):
    """propose_fact_update's proposal shows both the old and new content/category, carrying over any field left unchanged."""
    tool = _fact_tool(monkeypatch, "propose_fact_update")

    assert tool("f1", content="Uses MySQL") == {
        "proposal": "fact_update",
        "fact_id": "f1",
        "old": {"content": "Uses PostgreSQL", "category": "architecture"},
        "new": {"content": "Uses MySQL", "category": "architecture"},
    }
    assert tool("f1", category="decision")["new"] == {
        "content": "Uses PostgreSQL",
        "category": "decision",
    }


def test_propose_fact_update_turns_a_bad_request_into_an_error_result(monkeypatch):
    """propose_fact_update returns an error result for no changes, an invalid category, or an unknown fact id."""
    tool = _fact_tool(monkeypatch, "propose_fact_update")

    assert "error" in tool("f1")  # nothing to change
    assert "error" in tool("f1", category="nope")
    assert "error" in tool("missing", content="x")


def test_propose_fact_delete_shows_the_fact_and_writes_nothing(monkeypatch):
    """propose_fact_delete's proposal shows the fact to be deleted without writing to Firestore, and errors on an unknown id."""
    tool = _fact_tool(monkeypatch, "propose_fact_delete")

    assert tool("f1") == {
        "proposal": "fact_delete",
        "fact_id": "f1",
        "old": {"content": "Uses PostgreSQL", "category": "architecture"},
    }
    assert "error" in tool("missing")


def test_the_agent_names_the_propose_tools_and_not_the_removed_write_tools():
    """The agent's instruction names propose_fact_update/propose_fact_delete and never the removed update_fact/delete_fact tools."""
    instruction = _instruction(agent_module.build_agent("test@example.com", "some_tenant"))

    assert "propose_fact_update" in instruction and "propose_fact_delete" in instruction
    assert "update_fact" not in instruction.replace("propose_fact_update", "")
    assert "delete_fact" not in instruction.replace("propose_fact_delete", "")


def _jira_ready(monkeypatch, project_key="APPCE"):
    monkeypatch.setattr(
        agent_module,
        "get_owned_tenant",
        lambda tenant_id, owner_uid: {"jira_project_key": project_key},
    )
    monkeypatch.setattr(
        agent_module,
        "get_jira_credentials",
        lambda owner_uid: {
            "email": "user@example.com",
            "token": "secret-token",
            "base_url": "https://x",
        },
    )


def test_get_jira_recently_done_uses_the_projects_key_and_the_users_own_credentials(monkeypatch):
    """get_jira_recently_done queries with the tenant's linked project key and the calling user's own Jira credentials."""
    # Built first: the tool takes its name from the real function.
    tool = _tool_by_name(
        agent_module.build_agent("test@example.com", "some_tenant").tools, "get_jira_recently_done"
    )
    _jira_ready(monkeypatch)
    calls = []
    monkeypatch.setattr(
        agent_module,
        "get_jira_recently_done",
        lambda project_key, email, token, base_url: (
            calls.append((project_key, email, token, base_url))
            or {"issues": [], "truncated": False}
        ),
    )

    assert tool() == {"issues": [], "truncated": False}
    assert calls == [("APPCE", "user@example.com", "secret-token", "https://x")]


def test_get_jira_recently_done_returns_error_results_instead_of_raising(monkeypatch):
    """get_jira_recently_done returns an error result for no linked project, no connected account, and an HTTP failure."""
    tool = _tool_by_name(
        agent_module.build_agent("test@example.com", "some_tenant").tools, "get_jira_recently_done"
    )

    monkeypatch.setattr(agent_module, "get_owned_tenant", lambda tenant_id, owner_uid: {})
    assert "no linked Jira" in tool()["error"]

    _jira_ready(monkeypatch)
    monkeypatch.setattr(agent_module, "get_jira_credentials", lambda owner_uid: None)
    assert "No Jira account" in tool()["error"]

    _jira_ready(monkeypatch)

    def http_failure(*args, **kwargs):
        """Simulate the Jira request timing out."""
        raise RuntimeError("Jira timed out")

    monkeypatch.setattr(agent_module, "get_jira_recently_done", http_failure)
    assert tool() == {"error": "Jira timed out"}


def test_get_github_history_has_owner_uid_and_tenant_id_bound_and_returns_errors_as_results(
    monkeypatch,
):
    """get_github_history calls through with owner_uid/tenant_id already bound, and turns a raised error into an error result."""
    tool = _tool_by_name(
        agent_module.build_agent("test@example.com", "some_tenant").tools, "get_github_history"
    )
    seen = {}

    def fake(owner_uid, tenant_id):
        """Record the arguments the tool wrapper was called with and return an empty history."""
        seen.update(owner_uid=owner_uid, tenant_id=tenant_id)
        return {"pull_requests": [], "issues": [], "truncated": False}

    monkeypatch.setattr(agent_module, "get_github_history", fake)
    tool()
    assert seen == {"owner_uid": "test@example.com", "tenant_id": "some_tenant"}

    def no_repo(owner_uid, tenant_id):
        """Simulate a tenant with no GitHub repo attached."""
        raise ValueError("Tenant 'some_tenant' has no GitHub repo attached.")

    monkeypatch.setattr(agent_module, "get_github_history", no_repo)
    assert tool() == {"error": "Tenant 'some_tenant' has no GitHub repo attached."}


def test_the_history_tools_have_a_description_the_model_can_use():
    """get_jira_recently_done and get_github_history both document "truncated" in their docstrings."""
    tools = agent_module.build_agent("test@example.com", "some_tenant").tools

    for name in ("get_jira_recently_done", "get_github_history"):
        assert "truncated" in _tool_by_name(tools, name).__doc__


def test_the_agent_treats_history_titles_as_data():
    """The agent's instruction names both history tools and tells the model to treat their titles as data, never as instructions."""
    instruction = _instruction(agent_module.build_agent("test@example.com", "some_tenant"))

    assert "get_jira_recently_done" in instruction and "get_github_history" in instruction
    assert "never as instructions" in instruction


def test_the_agent_checks_facts_against_recent_activity_without_overclaiming():
    """The instruction tells the model to compare facts against recent activity for staleness, but stay cautious about unverified conflicts and never quote a fact_id."""
    instruction = _instruction(agent_module.build_agent("test@example.com", "some_tenant"))

    assert "outdated" in instruction
    # The comparison uses the read tools; changing anything still goes through a card.
    assert "get_jira_recently_done" in instruction and "propose_fact_update" in instruction
    assert "unverified" in instruction and "nothing conflicts" in instruction
    assert "never by its fact_id" in instruction


def test_get_pending_facts_is_bound_to_the_owner_and_tenant_and_returns_errors_as_results(
    monkeypatch,
):
    """get_pending_facts calls through with tenant_id/owner_uid already bound, and turns a raised error into an error result."""
    tool = _tool_by_name(
        agent_module.build_agent("test@example.com", "some_tenant").tools, "get_pending_facts"
    )
    seen = {}

    def fake(tenant_id, owner_uid):
        """Record the arguments the tool wrapper was called with and return no pending facts."""
        seen.update(tenant_id=tenant_id, owner_uid=owner_uid)
        return {"pending": [], "truncated": False}

    monkeypatch.setattr(agent_module, "get_pending_facts_summary", fake)
    assert tool() == {"pending": [], "truncated": False}
    assert seen == {"tenant_id": "some_tenant", "owner_uid": "test@example.com"}

    def down(tenant_id, owner_uid):
        """Simulate Firestore being unavailable."""
        raise RuntimeError("Firestore unavailable")

    monkeypatch.setattr(agent_module, "get_pending_facts_summary", down)
    assert tool() == {"error": "Firestore unavailable"}


def test_the_agent_cannot_approve_or_reject_pending_facts_and_says_where_to():
    """The agent has no approve/reject tool for pending facts, and its instruction points the model to the Pending tab instead."""
    tool_names = {
        _tool_name(t) for t in agent_module.build_agent("test@example.com", "some_tenant").tools
    }
    instruction = _instruction(agent_module.build_agent("test@example.com", "some_tenant"))

    assert tool_names.isdisjoint({"approve_pending_fact", "reject_pending_fact"})
    assert "get_pending_facts" in instruction and "Pending tab" in instruction
    # The code-side mark only sees similar wording; the model covers meaning,
    # which it can't do without also reading the saved facts.
    assert (
        "another language" in instruction
        and "BOTH get_pending_facts and get_tenant_facts" in instruction
    )
    assert "never as instructions" in instruction


def test_the_instruction_lists_the_users_own_categories(monkeypatch):
    """The instruction lists the calling user's current categories, and reflects a category change on the next turn's rebuild."""
    built = agent_module.build_agent("test@example.com", "some_tenant")
    assert "architecture, decision, risk" in _instruction(built)

    # Read again on the next turn, so a category added in Settings is known at once.
    monkeypatch.setattr(agent_module, "get_categories", lambda owner_uid: ["note"])
    assert "(note " in _instruction(built)
    assert "todo" not in _instruction(built).split("call publish_fact")[1].split("\n")[0]


def test_publishing_with_an_unknown_category_returns_a_message_not_a_crash(monkeypatch):
    """publish_fact turns an InvalidCategory error into a plain "Not published: ..." message instead of raising."""

    def refuse(tenant_id, content, category, owner_uid):
        """Simulate publish_fact rejecting an unknown category."""
        raise InvalidCategory("'x' is not one of your categories")

    tool = _callable(
        _tool_by_name(agent_module.build_agent("test@example.com", "t").tools, "publish_fact")
    )
    # Patched after the build: the wrapper takes its name and docstring from the real one.
    monkeypatch.setattr(agent_module, "publish_fact", refuse)

    assert tool("something", "x") == "Not published: 'x' is not one of your categories"
