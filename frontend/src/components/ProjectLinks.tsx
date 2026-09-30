import { useState } from "react";

import { setTenantLink, type JiraConnection, type Tenant } from "../api";
import ConfirmDialog from "./ConfirmDialog";
import "./ProjectLinks.css";

// Sidebar card, shown above the tabs, for viewing and editing the selected
// project's GitHub repo / Jira project key links (the Row component below
// handles both, in place, with its own edit/unlink affordances).

interface Props {
  idToken: string;
  tenant: Tenant;
  // null while the account status is still loading — no warning until it is
  // known, so the card doesn't flash "connect your account" on every load.
  githubConnected: boolean | null;
  jira: JiraConnection | null;
  // Called after a link was changed or removed, so the project list is re-read.
  onChanged: () => void;
}

// ready: linked, and the user's account is connected — live data works.
// needs-account: the project is linked but the account isn't, so nothing
// can be fetched. not-linked: the project has nothing linked at all.
type State = "ready" | "needs-account" | "not-linked";

const DOT: Record<State, string> = { ready: "●", "needs-account": "⚠", "not-linked": "○" };
const DOT_LABEL: Record<State, string> = {
  ready: "Linked",
  "needs-account": "Linked, but your account isn't connected",
  "not-linked": "Not linked",
};

// A link is only built from an http(s) address; anything else stays plain
// text rather than becoming a clickable "javascript:" URL.
function httpUrl(value: string | null | undefined): string | null {
  return value && /^https?:\/\//i.test(value) ? value.replace(/\/+$/, "") : null;
}

function stateOf(linked: string | null, accountConnected: boolean | null): State {
  if (!linked) return "not-linked";
  return accountConnected === false ? "needs-account" : "ready";
}

// A pasted repo address is a natural thing to type; reduce it to owner/name.
// Only a convenience: the server checks the result again.
function githubRepoFrom(raw: string): string {
  return raw.replace(/^https?:\/\/github\.com\//i, "").replace(/\.git$/i, "").replace(/\/+$/, "");
}

// A repo name is wrapped after its "/" rather than in the middle of a word:
// owner/ on one line, name on the next.
function breakable(value: string) {
  const parts = value.split("/");
  return parts.map((part, i) => (
    <span key={i}>
      {part}
      {i < parts.length - 1 && "/"}
      <wbr />
    </span>
  ));
}

interface RowProps {
  label: string;
  noun: string;
  state: State;
  value: string | null;
  href: string | null;
  placeholder: string;
  // What to say next to an unlinked row, and when the account isn't connected.
  linkHint: string;
  accountHint: string;
  normalize: (raw: string) => string;
  save: (value: string) => Promise<void>;
  remove: () => Promise<void>;
  removeMessage: string;
}

function Row({
  label,
  noun,
  state,
  value,
  href,
  placeholder,
  linkHint,
  accountHint,
  normalize,
  save,
  remove,
  removeMessage,
}: RowProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);

  function startEditing() {
    setDraft(value ?? "");
    setError(null);
    setEditing(true);
  }

  async function submit() {
    const next = normalize(draft.trim());
    if (!next) return;
    setBusy(true);
    setError(null);
    try {
      await save(next);
      setEditing(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save it. Please try again.");
    }
    setBusy(false);
  }

  async function confirmRemove() {
    setConfirming(false);
    setBusy(true);
    setError(null);
    try {
      await remove();
    } catch {
      setError("Couldn't unlink it. Please try again.");
    }
    setBusy(false);
  }

  return (
    <div className="project-link-row">
      <span className="project-link-label">{label}</span>
      <span className={`project-link-dot project-link-${state}`} role="img" aria-label={DOT_LABEL[state]} title={DOT_LABEL[state]}>
        {DOT[state]}
      </span>

      {editing ? (
        <span className="project-link-value">
          <span className="project-link-edit">
            <input
              autoFocus
              value={draft}
              placeholder={placeholder}
              aria-label={noun}
              disabled={busy}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") submit();
                if (e.key === "Escape") setEditing(false);
              }}
            />
            <button onClick={submit} disabled={busy || !draft.trim()}>
              Save
            </button>
            <button onClick={() => setEditing(false)} disabled={busy}>
              Cancel
            </button>
          </span>
          {error && <span className="project-link-error">{error}</span>}
        </span>
      ) : (
        <span className="project-link-value">
          <span className="project-link-line">
            <span className="project-link-text">
              {value ? (
                href ? (
                  <a href={href} target="_blank" rel="noopener noreferrer">
                    {breakable(value)} ↗
                  </a>
                ) : (
                  breakable(value)
                )
              ) : (
                <span className="project-link-none">Not linked</span>
              )}
            </span>
            <span className="project-link-actions">
              <button className="project-link-action" title={value ? `Change the ${noun}` : `Link a ${noun}`} onClick={startEditing} disabled={busy}>
                {value ? "✎" : "+"}
              </button>
              {value && (
                <button className="project-link-action" title={`Unlink the ${noun}`} onClick={() => setConfirming(true)} disabled={busy}>
                  ✕
                </button>
              )}
            </span>
          </span>
          {state === "not-linked" && <span className="project-link-hint">{linkHint}</span>}
          {state === "needs-account" && <span className="project-link-hint">{accountHint}</span>}
          {error && <span className="project-link-error">{error}</span>}
        </span>
      )}

      {confirming && (
        <ConfirmDialog
          title={`Unlink the ${noun}?`}
          message={removeMessage}
          confirmLabel="Unlink"
          cancelLabel="Keep"
          onCancel={() => setConfirming(false)}
          onConfirm={confirmRemove}
        />
      )}
    </div>
  );
}

function ProjectLinks({ idToken, tenant, githubConnected, jira, onChanged }: Props) {
  const repo = tenant.github_repo;
  const key = tenant.jira_project_key;
  const jiraBase = httpUrl(jira?.base_url);

  async function change(field: "github_repo" | "jira_project_key", value: string | null) {
    await setTenantLink(idToken, tenant.tenant_id, field, value);
    onChanged();
  }

  return (
    <div className="project-links">
      <Row
        label="GitHub"
        noun="GitHub repo"
        state={stateOf(repo, githubConnected)}
        value={repo}
        href={repo ? `https://github.com/${repo.split("/").map(encodeURIComponent).join("/")}` : null}
        placeholder="owner/repo"
        linkHint="Link a repo to see its pull requests and issues."
        accountHint="Connect your GitHub account in Settings."
        normalize={githubRepoFrom}
        save={(value) => change("github_repo", value)}
        remove={() => change("github_repo", null)}
        removeMessage="This project stops being polled for pull requests and issues. Facts already saved stay."
      />
      <Row
        label="Jira"
        noun="Jira project"
        state={stateOf(key, jira ? jira.connected : null)}
        value={key}
        href={key && jiraBase ? `${jiraBase}/browse/${encodeURIComponent(key)}` : null}
        placeholder="KEY"
        linkHint="Link a Jira project to see its open issues."
        accountHint="Connect your Jira account in Settings."
        normalize={(raw) => raw.toUpperCase()}
        save={(value) => change("jira_project_key", value)}
        remove={() => change("jira_project_key", null)}
        removeMessage="The assistant will no longer be able to look up this project's Jira issues. Nothing in Jira changes."
      />
    </div>
  );
}

export default ProjectLinks;
