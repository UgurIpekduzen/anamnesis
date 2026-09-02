from google.adk.agents.llm_agent import Agent

from src.facts import get_tenant_facts
from src.tenants import list_tenants

root_agent = Agent(
    model='gemini-2.5-flash',
    name='root_agent',
    description='Answers questions about the user\'s personal projects using stored facts.',
    instruction=(
        'You help the user recall information about their personal projects '
        '(tenants). Before calling get_tenant_facts, call list_tenants to '
        'find the exact tenant_id for the project the user means — never '
        'guess or transform the project name yourself. If no listed project '
        'clearly matches, ask the user to clarify.\n'
        'When calling get_tenant_facts, omit the category filter unless the '
        'user explicitly asks for a specific type of information (e.g. '
        '"what bugs are open" implies category=bug). Do not infer a '
        'category from general wording like "decided" or "chosen".'
    ),
    tools=[list_tenants, get_tenant_facts],
)
