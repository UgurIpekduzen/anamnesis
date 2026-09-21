import os

from google.adk.agents.llm_agent import Agent

from agent.history import make_history_limiter
from src.facts import delete_fact, get_tenant_facts, update_fact
from src.jira_client import get_jira_status
from src.publisher import publish_fact
from src.tenants import (
    add_tenant,
    delete_tenant,
    list_tenants,
    rename_tenant,
    set_git_repo_path,
    set_jira_project_key,
)


# A tool result stays in the session history for as many turns as the
# user's history window (src/settings.py) and is resent on every model
# call, so an unbounded fact list is an expensive one (APPCE-59).
MAX_FACTS_PER_TOOL_CALL = int(os.environ.get("MAX_FACTS_PER_TOOL_CALL", 50))


def build_agent(owner_uid: str) -> Agent:
    """Build an Agent scoped to one user.

    owner_uid must never be a parameter the LLM fills in — it comes from
    the caller's verified identity (see app/auth.py), not from anything
    the model or user says in chat. So instead of exposing the src.*
    functions directly as tools (which would put owner_uid in their
    tool-calling schema), each tool here is a thin wrapper with owner_uid
    already bound and dropped from the signature the model sees
    (see APPCE-47/APPCE-48).
    """

    def _list_tenants() -> list[dict]:
        return list_tenants(owner_uid)

    def _get_tenant_facts(tenant_id: str) -> list[dict]:
        return get_tenant_facts(tenant_id, owner_uid, limit=MAX_FACTS_PER_TOOL_CALL)

    def _publish_fact(tenant_id: str, content: str, category: str) -> str:
        return publish_fact(tenant_id, content, category, owner_uid)

    def _update_fact(
        tenant_id: str, fact_id: str, content: str | None = None, category: str | None = None
    ) -> None:
        update_fact(tenant_id, fact_id, owner_uid, content=content, category=category)

    def _delete_fact(tenant_id: str, fact_id: str) -> None:
        delete_fact(tenant_id, fact_id, owner_uid)

    def _add_tenant(name: str) -> str:
        return add_tenant(name, owner_uid)

    def _rename_tenant(tenant_id: str, new_name: str) -> None:
        rename_tenant(tenant_id, new_name, owner_uid)

    def _delete_tenant(tenant_id: str) -> None:
        delete_tenant(tenant_id, owner_uid)

    def _set_git_repo_path(tenant_id: str, git_repo_path: str) -> None:
        set_git_repo_path(tenant_id, git_repo_path, owner_uid)

    def _set_jira_project_key(tenant_id: str, jira_project_key: str) -> None:
        set_jira_project_key(tenant_id, jira_project_key, owner_uid)

    # Reuse each src.* function's own docstring so ADK's tool schema
    # (built from name + docstring) stays accurate without duplicating
    # the description here.
    for wrapper, original in [
        (_list_tenants, list_tenants),
        (_get_tenant_facts, get_tenant_facts),
        (_publish_fact, publish_fact),
        (_update_fact, update_fact),
        (_delete_fact, delete_fact),
        (_add_tenant, add_tenant),
        (_rename_tenant, rename_tenant),
        (_delete_tenant, delete_tenant),
        (_set_git_repo_path, set_git_repo_path),
        (_set_jira_project_key, set_jira_project_key),
    ]:
        wrapper.__name__ = original.__name__
        wrapper.__doc__ = original.__doc__

    # The model has to know the list can be cut short, or it would treat
    # a truncated list as the project's complete history.
    _get_tenant_facts.__doc__ += (
        f"\n\n    Only the {MAX_FACTS_PER_TOOL_CALL} most recent facts are returned, newest"
        " first — a project may have older ones that are not shown."
    )

    return Agent(
        model='gemini-2.5-flash',
        name='root_agent',
        before_model_callback=make_history_limiter(owner_uid),
        description='Answers questions about the user\'s personal projects, records new facts, registers new projects, and checks live Jira status.',
        instruction=(
            'You help the user recall and record information about their '
            'personal projects (tenants). Before calling get_tenant_facts, '
            'publish_fact, or get_jira_status, call list_tenants to find the '
            'exact tenant_id (and, for Jira questions, jira_project_key) for '
            'the project the user means — never guess or transform the project '
            'name yourself. If no listed project clearly matches, ask the user '
            'to clarify.\n'
            'get_tenant_facts returns all facts for a project, each with a '
            'fact_id and its category — use the category to answer the '
            'user\'s question (e.g. only mention bugs if they asked about '
            'bugs) rather than filtering the call itself.\n'
            'When the user asks you to remember, note, or record something '
            'about a project, call publish_fact with tenant_id, content, and '
            'a category (architecture, decision, bug, status, or todo — ask '
            'the user if it is unclear which one fits).\n'
            'When the user asks you to edit or correct a saved note/fact, '
            'call get_tenant_facts to find the matching fact_id (ask the user '
            'to clarify if more than one fact could match), then call '
            'update_fact with that fact_id and only the field(s) that '
            'changed.\n'
            'When the user asks you to delete or remove a saved note/fact, '
            'find the matching fact_id via get_tenant_facts, show the user '
            'its content, confirm before calling delete_fact — this is '
            'irreversible.\n'
            'When the user asks you to add, register, or create a new project, '
            'first call list_tenants to make sure it does not already exist, '
            'then call add_tenant with just the project name — do not invent a '
            'tenant_id yourself, add_tenant generates it from the name.\n'
            'When the user tells you a project\'s Jira project key (e.g. "the '
            'Jira key for TMDB is ADVBK"), resolve the tenant_id via '
            'list_tenants first, then call set_jira_project_key with that '
            'tenant_id and the key.\n'
            'When the user asks you to rename a project, resolve the tenant_id '
            'via list_tenants first, then call rename_tenant with that '
            'tenant_id and the new name.\n'
            'When the user asks you to delete or remove a project, resolve the '
            'tenant_id via list_tenants first, then confirm with the user '
            '(name the project and say this will also delete all of its saved '
            'facts) before calling delete_tenant — this is irreversible.\n'
            'When the user tells you a project\'s local git repo path (e.g. '
            '"the repo for recruiter_ai is /home/user/repos/recruiter_ai"), '
            'resolve the tenant_id via list_tenants first, then call '
            'set_git_repo_path with that tenant_id and the path. Mention that '
            'this path is specific to the machine it was set on.\n'
            'When the user asks about open tickets, tasks, or issues for a '
            'project, look up that tenant\'s jira_project_key via list_tenants '
            'and call get_jira_status with it — this is live Jira data, not '
            'stored facts. If the tenant has no jira_project_key, tell the '
            'user there is no linked Jira project instead of guessing one.'
        ),
        tools=[
            _list_tenants,
            _get_tenant_facts,
            _publish_fact,
            _update_fact,
            _delete_fact,
            _add_tenant,
            _rename_tenant,
            _delete_tenant,
            _set_git_repo_path,
            _set_jira_project_key,
            get_jira_status,
        ],
    )
