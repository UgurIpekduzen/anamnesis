import { useEffect, useState, type ReactNode } from "react";

import {
  getGithubStatus,
  getJiraStatus,
  type GithubItem,
  type GithubStatus,
  type JiraStatus,
} from "../api";
import "./StatusPanel.css";

// Sidebar "Status" tab content: read-only snapshot of the selected project's
// open Jira issues and GitHub pull requests/issues. Each of the three lists
// (Jira issues, GitHub pull requests, GitHub issues) is its own collapsible,
// independently-scrolling <details> — same pattern as TracePanel — so a
// long list in one doesn't push the others out of view.

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
      <GithubSections status={github} />
    </div>
  );
}

// What to say when there is nothing to list, and how to fix it.
function Empty({ state, service, hint }: { state: string; service: string; hint: string }) {
  if (state === "not_linked")
    return (
      <p className="status-hint">
        No {service} linked. {hint}
      </p>
    );
  if (state === "not_connected")
    return <p className="status-hint">Connect your {service} account in Settings.</p>;
  return null;
}

// A collapsible, independently-scrolling area — the shared shell every
// status list (Jira issues, GitHub pull requests, GitHub issues) renders
// inside of.
function StatusDetails({
  title,
  scope,
  children,
}: {
  title: string;
  scope?: string;
  children: ReactNode;
}) {
  return (
    <details className="status-details" open>
      <summary>
        <span className="status-details-title">{title}</span>
        {scope && <span className="status-scope"> · {scope}</span>}
      </summary>
      <div className="status-details-body">{children}</div>
    </details>
  );
}

function JiraSection({ status }: { status: Loaded<JiraStatus> }) {
  const scope = status !== "loading" && status.state === "ok" ? status.project_key : undefined;
  return (
    <StatusDetails title="Open Jira issues" scope={scope}>
      {status === "loading" ? (
        <p className="status-hint">Loading…</p>
      ) : status.state === "error" ? (
        <p className="status-error">{status.message}</p>
      ) : status.state !== "ok" ? (
        <Empty
          state={status.state}
          service="Jira project"
          hint="Link one from the project card above."
        />
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
          {status.truncated && (
            <p className="status-hint">
              More are open than shown (the most recently updated first).
            </p>
          )}
        </>
      )}
    </StatusDetails>
  );
}

function GithubList({ items }: { items: GithubItem[] }) {
  if (items.length === 0) return <p className="status-hint">None open.</p>;
  return (
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
  );
}

// Loading/error/not-linked states don't yet know which lists there'll be,
// so they share one generic "GitHub" box; once connected, pull requests and
// issues split into their own boxes so one long list doesn't push the other
// out of view.
function GithubSections({ status }: { status: Loaded<GithubStatus> }) {
  if (status === "loading") {
    return (
      <StatusDetails title="GitHub">
        <p className="status-hint">Loading…</p>
      </StatusDetails>
    );
  }
  if (status.state === "error") {
    return (
      <StatusDetails title="GitHub">
        <p className="status-error">{status.message}</p>
      </StatusDetails>
    );
  }
  if (status.state !== "ok") {
    return (
      <StatusDetails title="GitHub">
        <Empty state={status.state} service="GitHub repo" hint="Link one from the project card above." />
      </StatusDetails>
    );
  }
  return (
    <>
      <StatusDetails title="Pull requests" scope={status.repo}>
        <GithubList items={status.pull_requests} />
      </StatusDetails>
      <StatusDetails title="Issues" scope={status.repo}>
        <GithubList items={status.issues} />
      </StatusDetails>
    </>
  );
}

export default StatusPanel;
