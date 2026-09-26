# Project structure

Where code lives, which way it may depend on other code, and where new code
goes. The dependency rule is checked by `test/test_architecture.py`, so it
can't drift.

## Layout

```
api/                    the HTTP and WebSocket layer
  main.py               app setup only: middleware, routers, static files
  routers/              one router per area of the API
  deps.py               sign-in (ID token check, allowlist)
  internal_auth.py      the scheduler's identity
  runner.py, session_memory.py   the agent's runner and its memory
agent/                  the ADK agent: its instruction, its tools, its history limit
src/                    the domain code, grouped by what it is about
  core/                 env, logging, Firestore and Pub/Sub clients, token encryption
  accounts/             who may sign in, per-user settings, daily usage
  projects/             projects (tenants), saved chat turns, project-key and repo checks
  facts/                facts and pending facts, categories, the write path (publisher)
  integrations/         github/ and jira/ (client, connections, ...), and their status
  tools/                maintenance commands: db_backup, key_rotation, setup_pubsub
  subscriber.py         the Pub/Sub push endpoint (an entry point, see below)
eval/                   evals that run the real model (groundedness, prompt injection)
frontend/               the React app
terraform/              infrastructure
test/                   unit tests; test/integration/ runs against the emulators
docs/                   this file
```

## Dependency direction

An import may only point to a package of a **lower** rank:

```
api  ->  agent  ->  src/integrations  ->  src/facts  ->  src/projects, src/accounts  ->  src/core
```

Each package may use anything to its right. (Routers reach `agent` through
`api/runner.py`; they call `src` directly for everything else.)

- `src/tools` and `src/subscriber.py` are entry points: they may use any `src`
  package, and nothing imports them.
- `src/projects` and `src/accounts` are on the same rank and know nothing of
  each other. `src/facts` uses `src/projects` (a fact belongs to a project).
- `src` never imports `api`, `agent` or `eval`.
- Routers don't import each other. What two routers share goes in `src/` or
  `api/deps.py`.
- Where a bare name would be unclear (`categories`, `settings`, `tenants`),
  import the module and call through it (`from src.facts import categories`),
  so the reader sees where the name comes from.

`test/test_architecture.py` fails on an import that points up or sideways. A
new `src` package has to be given a rank there, and listed above.

## Where new code goes

| You are adding | Put it in |
|---|---|
| an endpoint | the router of its area in `api/routers/` (a new file for a new area, then `include_router` in `api/main.py`). Its request model sits next to it. The router calls `src`; it holds no business rule |
| a rule or a Firestore read/write | the `src` package it is about (`facts`, `projects`, `accounts`) |
| a call to GitHub or Jira | `src/integrations/<service>/` |
| an agent tool | `agent/agent.py`, as a thin wrapper over a `src` function. A tool that writes must be wrapped in `require_confirmation` |
| a maintenance command | `src/tools/`, with a `task` entry in `Taskfile.yml` |
| a check that a value has a plain shape | `src/projects/validation.py` |

## Rules of thumb

- **Size.** A file past 300-400 lines is a candidate for splitting.
  `api/routers/chat.py` (the chat socket) is at that limit.
- **Comments say why**, in English, and match the density around them. A module
  starts with a short docstring: what it is responsible for.
- **Lazy imports.** ADK and Pub/Sub are heavy to import; the endpoints that
  need them import them inside a small wrapper function that is still a real
  module-level name (see `pending.py`, `chat.py`), so tests can patch it.
- **Tests patch the module that uses a name**, not the one that defines it:
  `monkeypatch.setattr(tenants_router, "add_tenant", ...)`, not
  `src.projects.tenants.add_tenant`. Import the router module under a name
  that can't clash with a fixture (`from api.routers import chat as chat_router`).
- **No test may need real GCP.** Unit tests need nothing; integration tests
  need the emulators (`task test:integration`).

## Entry points that must not move

Something outside the code names each of these. Moving one is a coordinated
change, not a refactor.

| Entry point | Named by |
|---|---|
| `api.main:app` | `Dockerfile`, `Dockerfile.app` |
| `src.subscriber` | the Cloud Run command in `terraform/cloud_run.tf` |
| `/internal/poll-github` | the Cloud Scheduler target in `terraform/github_poller.tf` |
| `src.tools.*`, `eval.*` | `Taskfile.yml` |

The deploy applies Terraform before it builds the image, so a Terraform change
that names a module the deployed image doesn't have yet breaks the revision.
Change such a name in two steps: ship an image that answers to both names, then
change Terraform.

## Not done yet

- `test/` is flat and named after the area (`test_api_tenants.py`,
  `test_categories_user.py`). Mirroring `src/` and `api/routers/` is planned.
- `frontend/src/components/` holds one file per component, with its own CSS.
  Grouping it by feature (`chat`, `facts`, `pending`, `status`, `settings`,
  `projects`, `account`) is planned.
- `agent/agent.py` builds all of the agent's tools in one function. Splitting
  them by topic changes the tool schemas the model sees, so it has to be
  measured with `task eval:groundedness`.
