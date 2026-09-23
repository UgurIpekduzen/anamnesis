# anamnesis

## Setup — one-time secret provisioning

After `task tf:apply` has created the Secret Manager secrets, their values
still need to be added manually — Terraform only creates the empty secret
container, never the value itself (so it never ends up in state or version
control).

- **`jira-api-token`**: add your Jira API token's value
  ```
  echo -n "<your Jira API token>" | task gcloud -- secrets versions add jira-api-token --data-file=-
  ```
- **`github-token-encryption-key`**: run once, generates and stores a Fernet
  key used to encrypt per-user GitHub tokens before they're saved to
  Firestore (see APPCE-79). Safe to re-run — it skips if a version already
  exists, since overwriting it would break any tokens already encrypted with
  the old key.
  ```
  task secrets:github-key:init
  ```
  Then, for the local `api` container to encrypt/decrypt with the same key
  as production, fetch it into your local `.env` (see `.env.example`):
  ```
  task secrets:github-key:pull
  ```
