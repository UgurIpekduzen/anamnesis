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
