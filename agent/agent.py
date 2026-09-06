from google.adk.agents.llm_agent import Agent

from src.facts import get_tenant_facts
from src.publisher import publish_fact
from src.tenants import add_tenant, list_tenants

root_agent = Agent(
    model='gemini-2.5-flash',
    name='root_agent',
    description='Answers questions about the user\'s personal projects, records new facts, and registers new projects.',
    instruction=(
        'You help the user recall and record information about their '
        'personal projects (tenants). Before calling get_tenant_facts or '
        'publish_fact, call list_tenants to find the exact tenant_id for '
        'the project the user means — never guess or transform the project '
        'name yourself. If no listed project clearly matches, ask the user '
        'to clarify.\n'
        'When calling get_tenant_facts, omit the category filter unless the '
        'user explicitly asks for a specific type of information (e.g. '
        '"what bugs are open" implies category=bug). Do not infer a '
        'category from general wording like "decided" or "chosen".\n'
        'When the user asks you to remember, note, or record something '
        'about a project, call publish_fact with tenant_id, content, and '
        'a category (architecture, decision, bug, status, or todo — ask '
        'the user if it is unclear which one fits).\n'
        'When the user asks you to add, register, or create a new project, '
        'first call list_tenants to make sure it does not already exist, '
        'then call add_tenant with just the project name — do not invent a '
        'tenant_id yourself, add_tenant generates it from the name.'
    ),
    tools=[list_tenants, get_tenant_facts, publish_fact, add_tenant],
)
