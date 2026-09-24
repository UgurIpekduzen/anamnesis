import type { JiraConnection, Tenant } from "../api";
import "./ProjectLinks.css";

interface Props {
  tenant: Tenant;
  // null while the account status is still loading — no warning until it is
  // known, so the card doesn't flash "connect your account" on every load.
  githubConnected: boolean | null;
  jira: JiraConnection | null;
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

interface RowProps {
  label: string;
  state: State;
  value: string | null;
  href: string | null;
  fixHint: string;
}

function Row({ label, state, value, href, fixHint }: RowProps) {
  return (
    <div className="project-link-row">
      <span className="project-link-label">{label}</span>
      <span className={`project-link-dot project-link-${state}`} role="img" aria-label={DOT_LABEL[state]} title={DOT_LABEL[state]}>
        {DOT[state]}
      </span>
      <span className="project-link-value">
        {value ? (
          href ? (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {value} ↗
            </a>
          ) : (
            value
          )
        ) : (
          <span className="project-link-none">Not linked</span>
        )}
        {state !== "ready" && <span className="project-link-hint">{fixHint}</span>}
      </span>
    </div>
  );
}

function ProjectLinks({ tenant, githubConnected, jira }: Props) {
  const repo = tenant.github_repo;
  const key = tenant.jira_project_key;
  const jiraBase = httpUrl(jira?.base_url);

  return (
    <div className="project-links">
      <Row
        label="GitHub"
        state={stateOf(repo, githubConnected)}
        value={repo}
        href={repo ? `https://github.com/${repo.split("/").map(encodeURIComponent).join("/")}` : null}
        fixHint={
          repo
            ? "Connect your GitHub account in Settings."
            : 'Ask the assistant, e.g. "link this project to owner/repo".'
        }
      />
      <Row
        label="Jira"
        state={stateOf(key, jira ? jira.connected : null)}
        value={key}
        href={key && jiraBase ? `${jiraBase}/browse/${encodeURIComponent(key)}` : null}
        fixHint={
          key
            ? "Connect your Jira account in Settings."
            : 'Ask the assistant, e.g. "the Jira key is ABC".'
        }
      />
    </div>
  );
}

export default ProjectLinks;
