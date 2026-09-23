import agent.agent as agent_module


def test_the_agents_facts_tool_is_capped_and_says_so():
    tool_agent = agent_module.build_agent("test@example.com", "some_tenant")
    tool = next(t for t in tool_agent.tools if t.__name__ == "get_tenant_facts")

    # The wrapper looks get_tenant_facts up at call time, so patching after
    # build_agent leaves the docstring copy (which needs the real one) alone.
    seen = {}

    def fake_get_tenant_facts(tenant_id, owner_uid, limit=None):
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

    assert seen == {"tenant_id": "some_tenant", "owner_uid": "test@example.com", "limit": agent_module.MAX_FACTS_PER_TOOL_CALL}
    # Without this the model would read a truncated list as the whole history.
    assert "most recent" in tool.__doc__


def test_set_github_repo_has_owner_uid_and_tenant_id_bound():
    tool_agent = agent_module.build_agent("test@example.com", "some_tenant")
    tool = next(t for t in tool_agent.tools if t.__name__ == "set_github_repo")

    seen = {}

    def fake_set_github_repo(tenant_id, github_repo, owner_uid):
        seen.update(tenant_id=tenant_id, github_repo=github_repo, owner_uid=owner_uid)

    original = agent_module.set_github_repo
    agent_module.set_github_repo = fake_set_github_repo
    try:
        # The model only ever supplies github_repo — neither tenant_id nor
        # owner_uid is part of the callable signature it sees (APPCE-47/48).
        tool("owner/repo")
    finally:
        agent_module.set_github_repo = original

    assert seen == {"tenant_id": "some_tenant", "github_repo": "owner/repo", "owner_uid": "test@example.com"}


def test_get_github_status_has_owner_uid_and_tenant_id_bound():
    tool_agent = agent_module.build_agent("test@example.com", "some_tenant")
    tool = next(t for t in tool_agent.tools if t.__name__ == "get_github_status")

    seen = {}

    def fake_get_github_status(owner_uid, tenant_id):
        seen.update(owner_uid=owner_uid, tenant_id=tenant_id)
        return {"pull_requests": [], "issues": []}

    original = agent_module.get_github_status
    agent_module.get_github_status = fake_get_github_status
    try:
        tool()  # no arguments — both are bound at build time
    finally:
        agent_module.get_github_status = original

    assert seen == {"owner_uid": "test@example.com", "tenant_id": "some_tenant"}


def test_get_jira_status_resolves_the_project_key_from_the_tenant():
    tool_agent = agent_module.build_agent("test@example.com", "some_tenant")
    tool = next(t for t in tool_agent.tools if t.__name__ == "get_jira_status")

    calls = []

    original_owned = agent_module.get_owned_tenant
    original_status = agent_module.get_jira_status
    agent_module.get_owned_tenant = lambda tenant_id, owner_uid: {"jira_project_key": "APPCE"}
    agent_module.get_jira_status = lambda project_key: calls.append(project_key) or [{"key": "APPCE-1"}]
    try:
        result = tool()
    finally:
        agent_module.get_owned_tenant = original_owned
        agent_module.get_jira_status = original_status

    assert calls == ["APPCE"]
    assert result == [{"key": "APPCE-1"}]


def test_get_jira_status_returns_an_error_result_when_the_tenant_has_no_linked_project():
    # Not a raised exception: ADK doesn't turn an uncaught one into a tool
    # result the model can read, it crashes the whole turn instead (see
    # APPCE-83) — this must come back as a normal {"error": ...} result.
    tool_agent = agent_module.build_agent("test@example.com", "some_tenant")
    tool = next(t for t in tool_agent.tools if t.__name__ == "get_jira_status")

    original_owned = agent_module.get_owned_tenant
    agent_module.get_owned_tenant = lambda tenant_id, owner_uid: {}
    try:
        result = tool()
    finally:
        agent_module.get_owned_tenant = original_owned

    assert result == {"error": "This project has no linked Jira project key."}


def test_get_github_status_returns_an_error_result_instead_of_raising():
    tool_agent = agent_module.build_agent("test@example.com", "some_tenant")
    tool = next(t for t in tool_agent.tools if t.__name__ == "get_github_status")

    original = agent_module.get_github_status
    agent_module.get_github_status = lambda owner_uid, tenant_id: (_ for _ in ()).throw(
        ValueError("Tenant 'some_tenant' has no GitHub repo attached.")
    )
    try:
        result = tool()
    finally:
        agent_module.get_github_status = original

    assert result == {"error": "Tenant 'some_tenant' has no GitHub repo attached."}


def test_set_github_repo_returns_an_error_result_for_a_malformed_repo():
    tool_agent = agent_module.build_agent("test@example.com", "some_tenant")
    tool = next(t for t in tool_agent.tools if t.__name__ == "set_github_repo")

    original = agent_module.set_github_repo
    agent_module.set_github_repo = lambda tenant_id, github_repo, owner_uid: (_ for _ in ()).throw(
        ValueError("'not-a-repo' doesn't look like a GitHub 'owner/name' repo.")
    )
    try:
        result = tool("not-a-repo")
    finally:
        agent_module.set_github_repo = original

    assert result == {"error": "'not-a-repo' doesn't look like a GitHub 'owner/name' repo."}


def test_tenant_lifecycle_tools_are_not_exposed_to_the_model():
    tool_agent = agent_module.build_agent("test@example.com", "some_tenant")
    tool_names = {t.__name__ for t in tool_agent.tools}

    # Creating/renaming/deleting projects is UI-only now (see api/main.py's
    # /tenants endpoints) — the agent has nothing to scope those to.
    assert tool_names.isdisjoint({"list_tenants", "add_tenant", "rename_tenant", "delete_tenant"})
