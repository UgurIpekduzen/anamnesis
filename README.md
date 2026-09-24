# anamnesis

## Setup — one-time secret provisioning

After `task tf:apply` has created the Secret Manager secrets, their values
still need to be added manually — Terraform only creates the empty secret
container, never the value itself (so it never ends up in state or version
control).

- **`github-token-encryption-key`**: run once, generates and stores a Fernet
  key used to encrypt per-user GitHub and Jira credentials before they're
  saved to Firestore (see APPCE-79, APPCE-87). Safe to re-run — it skips if
  a version already exists, since overwriting it would break any secrets
  already encrypted with the old key.
  ```
  task secrets:github-key:init
  ```
  Then, for the local `api` container to encrypt/decrypt with the same key
  as production, fetch it into your local `.env` (see `.env.example`):
  ```
  task secrets:github-key:pull
  ```

## Encryption key: rotation and recovery

Every user's GitHub and Jira token is encrypted with the key in the
`github-token-encryption-key` secret before it is stored (APPCE-79,
APPCE-87). The secret can hold several keys, separated by commas, newest
first: new tokens are encrypted with the first, and every key is tried when
one is read. That is what makes a rotation gradual and lossless.

### Rotating the key

Do this on a schedule, or straight away if the key may have leaked.

The running app must already be a version that reads a list of keys
(APPCE-103). An older one reads `new,old` as a single, invalid key and fails
on the first token it touches; `rotate` checks this and refuses otherwise.

Run the tasks in this order:

```
task secrets:github-key:rotate      # add a new key in front of the current one
task secrets:github-key:reload      # start a new revision so the app loads it
task secrets:github-key:reencrypt   # re-write every stored token with the new key
task secrets:github-key:retire      # drop the old key, disable its secret versions
task secrets:github-key:reload      # load the single remaining key
```

- After `rotate` nothing is lost: old tokens still read with the old key,
  which is still in the list. Only one rotation can run at a time; `rotate`
  refuses to start while two keys are stored.
- `reencrypt` is safe to re-run. It reports any token that no configured key
  can read (with the account it belongs to, never the token) and carries on.
- `retire` first checks that every stored token reads with the new key
  **alone**. If any doesn't, it stops and changes nothing; run `reencrypt`
  again, or have that user reconnect, and retry.
- `reload` adds a label to `anamnesis-app` to force a new revision, because
  a secret marked `latest` is only resolved when a revision starts. The next
  `terraform plan` shows that label as drift; applying it is harmless.
- Never disable the newest secret version by hand. `latest` always means the
  newest version, disabled or not, and reading a disabled one fails, so the
  app could no longer start. `retire` is safe: it adds the new version first
  and only then disables the older ones.
- Refresh your local `.env` with `task secrets:github-key:pull` afterwards,
  so the local `api` container uses the same keys.

### If the key is lost or damaged

Without the key the stored tokens cannot be decrypted, by anyone:

- In chat, the GitHub and Jira tools answer "The saved token can't be
  decrypted (the encryption key has changed). Reconnect it in Settings."
- GitHub polling counts the failure per project in its summary log line
  (`error_count`).
- Settings still shows the account as connected, because it only checks that
  a record exists. Reconnecting overwrites the record, so each user can fix
  their own by entering the token again.

Recovering the old key, if a copy exists:

1. `task secrets:github-key:pull` prints the newest key. A disabled older
   version can be read again after re-enabling it:
   `docker compose run --rm gcloud secrets versions enable <N> --secret=github-token-encryption-key`
2. Add a new version holding both keys, newest first (`new,old`), and run
   `task secrets:github-key:reload`. Then run `reencrypt` and `retire` as
   above.

If no copy of the key exists anywhere, the tokens are gone for good and
every user reconnects. To avoid that:

- `terraform destroy` deletes this secret and all its versions. Do not run
  it against a live deployment.
- Keep one offline copy of the current key (a password manager), since
  Secret Manager is otherwise the only place it lives besides your local
  `.env`.
