import agent.agent as agent_module


def test_the_agents_facts_tool_is_capped_and_says_so():
    tool_agent = agent_module.build_agent("test@example.com")
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
        tool("some_tenant")
    finally:
        agent_module.get_tenant_facts = original

    assert seen["limit"] == agent_module.MAX_FACTS_PER_TOOL_CALL
    assert seen["owner_uid"] == "test@example.com"
    # Without this the model would read a truncated list as the whole history.
    assert "most recent" in tool.__doc__


def test_set_github_repo_has_owner_uid_bound_and_dropped_from_the_model_facing_signature():
    tool_agent = agent_module.build_agent("test@example.com")
    tool = next(t for t in tool_agent.tools if t.__name__ == "set_github_repo")

    seen = {}

    def fake_set_github_repo(tenant_id, github_repo, owner_uid):
        seen.update(tenant_id=tenant_id, github_repo=github_repo, owner_uid=owner_uid)

    original = agent_module.set_github_repo
    agent_module.set_github_repo = fake_set_github_repo
    try:
        # The model only ever supplies these two — owner_uid must not be
        # part of the callable signature it sees (see APPCE-47/48).
        tool("some_tenant", "owner/repo")
    finally:
        agent_module.set_github_repo = original

    assert seen == {"tenant_id": "some_tenant", "github_repo": "owner/repo", "owner_uid": "test@example.com"}
