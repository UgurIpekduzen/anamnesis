# Security policy

Anamnesis is a personal learning project maintained by one person. It doesn't accept outside contributions or issues, but a private report of a vulnerability is always welcome. Reports are handled on a best-effort basis, with no response-time guarantee.

## Reporting a vulnerability

Please report a vulnerability **privately**, not in a public issue: use the
["Report a vulnerability" button](../../security/advisories/new) on the
repository's Security tab (GitHub private vulnerability reporting). Say what
you found, how to reproduce it, and what you think the impact is.

Only the `main` branch is supported.

## Scope

In scope: the code in this repository — the API, the agent and its tools, the
frontend, and the deployment configuration. Of particular interest are ways to
read another user's data, to make the agent act on text written by someone
else (prompt injection), or to recover a stored GitHub or Jira credential.

Please do **not**:

- run scans or load tests against any live deployment of this project;
- access, change or delete data that isn't yours;
- test social engineering or physical attacks.

A local copy (see the README) is the place to try things out.
