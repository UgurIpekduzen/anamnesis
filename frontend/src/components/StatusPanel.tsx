import { useEffect, useState } from "react";

import {
  getGithubStatus,
  getJiraStatus,
  type GithubItem,
  type GithubStatus,
  type JiraStatus,
} from "../api";
import "./StatusPanel.css";

interface Props {
  idToken: string;
  tenantId: string;
  // Bumped by the parent to read both again.
  refreshKey: number;
}

// Loading is its own value: a failed call is shown as an error in that
// section, and the other section still renders.
type Loaded<T> = T | "loading";

function StatusPanel({ idToken, tenantId, refreshKey }: Props) {
  const [jira, setJira] = useState<Loaded<JiraStatus>>("loading");
  const [github, setGithub] = useState<Loaded<GithubStatus>>("loading");

  useEffect(() => {
    let cancelled = false;
    setJira("loading");
    setGithub("loading");
    // Two independent reads: one slow or failing service must not hold up or
    // hide the other.
    getJiraStatus(idToken, tenantId)
      .then((s) => !cancelled && setJira(s))
      .catch(() => !cancelled && setJira({ state: "error", message: "Couldn't load Jira." }));
    getGithubStatus(idToken, tenantId)
      .then((s) => !cancelled && setGithub(s))
      .catch(() => !cancelled && setGithub({ state: "error", message: "Couldn't load GitHub." }));
    return () => {
      cancelled = true;
    };
  }, [idToken, tenantId, refreshKey]);

  return (
    <div className="status-panel">
      <JiraSection status={jira} />
      <GithubSection status={github} />
    </div>
  );
}

// What to say when there is nothing to list, and how to fix it.
function Empty({ state, service, hint }: { state: string; service: string; hint: string }) {
  if (state === "not_linked") return <p className="status-hint">No {service} linked. {hint}</p>;
  if (state === "not_connected") return <p className="status-hint">Connect your {service} account in Settings.</p>;
  return null;
}

function JiraSection({ status }: { status: Loaded<JiraStatus> }) {
  return (
    <section className="status-section">
      <h3>
        Open Jira issues
        {status !== "loading" && status.state === "ok" && <span className="status-scope"> · {status.project_key}</span>}
      </h3>
      {status === "loading" ? (
        <p className="status-hint">Loading…</p>
      ) : status.state === "error" ? (
        <p className="status-error">{status.message}</p>
      ) : status.state !== "ok" ? (
        <Empty state={status.state} service="Jira project" hint="Link one from the project card above." />
      ) : status.issues.length === 0 ? (
        <p className="status-hint">Nothing open.</p>
      ) : (
        <>
          <ul className="status-list">
            {status.issues.map((issue) => (
              <li key={issue.key}>
                <a href={issue.url} target="_blank" rel="noopener noreferrer">
                  {issue.key}
                </a>
                <span className="status-pill">{issue.status}</span>
                <span className="status-title">{issue.summary}</span>
              </li>
            ))}
          </ul>
          {status.truncated && <p className="status-hint">More are open than shown (the most recently updated first).</p>}
        </>
      )}
    </section>
  );
}

function GithubList({ title, items }: { title: string; items: GithubItem[] }) {
  return (
    <>
      <h4>{title}</h4>
      {items.length === 0 ? (
        <p className="status-hint">None open.</p>
      ) : (
        <ul className="status-list">
          {items.map((item) => (
            <li key={item.number}>
              <a href={item.url} target="_blank" rel="noopener noreferrer">
                #{item.number}
              </a>
              <span className="status-title">{item.title}</span>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

function GithubSection({ status }: { status: Loaded<GithubStatus> }) {
  return (
    <section className="status-section">
      <h3>
        Open on GitHub
        {status !== "loading" && status.state === "ok" && <span className="status-scope"> · {status.repo}</span>}
      </h3>
      {status === "loading" ? (
        <p className="status-hint">Loading…</p>
      ) : status.state === "error" ? (
        <p className="status-error">{status.message}</p>
      ) : status.state !== "ok" ? (
        <Empty state={status.state} service="GitHub repo" hint="Link one from the project card above." />
      ) : (
        <>
          <GithubList title="Pull requests" items={status.pull_requests} />
          <GithubList title="Issues" items={status.issues} />
        </>
      )}
    </section>
  );
}

export default StatusPanel;
