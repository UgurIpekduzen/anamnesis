from google.adk.agents.llm_agent import Agent

from src.facts import get_tenant_facts
from src.jira_client import get_jira_status
from src.publisher import publish_fact
from src.tenants import add_tenant, list_tenants, set_jira_project_key

root_agent = Agent(
    model='gemini-2.5-flash',
    name='root_agent',
    description='Answers questions about the user\'s personal projects, records new facts, registers new projects, and checks live Jira status.',
    instruction=(
        'You help the user recall and record information about their '
        'personal projects (tenants). Before calling get_tenant_facts, '
        'publish_fact, or get_jira_status, call list_tenants to find the '
        'exact tenant_id (and, for Jira questions, jira_project_key) for '
        'the project the user means — never guess or transform the project '
        'name yourself. If no listed project clearly matches, ask the user '
        'to clarify.\n'
        'get_tenant_facts returns all facts for a project, each with its '
        'category — use that to answer the user\'s question (e.g. only '
        'mention bugs if they asked about bugs) rather than filtering the '
        'call itself.\n'
        'When the user asks you to remember, note, or record something '
        'about a project, call publish_fact with tenant_id, content, and '
        'a category (architecture, decision, bug, status, or todo — ask '
        'the user if it is unclear which one fits).\n'
        'When the user asks you to add, register, or create a new project, '
        'first call list_tenants to make sure it does not already exist, '
        'then call add_tenant with just the project name — do not invent a '
        'tenant_id yourself, add_tenant generates it from the name.\n'
        'When the user tells you a project\'s Jira project key (e.g. "the '
        'Jira key for TMDB is ADVBK"), resolve the tenant_id via '
        'list_tenants first, then call set_jira_project_key with that '
        'tenant_id and the key.\n'
        'When the user asks about open tickets, tasks, or issues for a '
        'project, look up that tenant\'s jira_project_key via list_tenants '
        'and call get_jira_status with it — this is live Jira data, not '
        'stored facts. If the tenant has no jira_project_key, tell the '
        'user there is no linked Jira project instead of guessing one.'
    ),
    tools=[list_tenants, get_tenant_facts, publish_fact, add_tenant, set_jira_project_key, get_jira_status],
)
