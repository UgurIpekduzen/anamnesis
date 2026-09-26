import { API_BASE } from "./client";

// What is open in the project's linked Jira project and GitHub repo, read
// live on the server with the user's own credentials (APPCE-110). "state"
// says whether there is anything to show and, if not, why.
export interface JiraIssue {
  key: string;
  type: string;
  status: string;
  summary: string;
  url: string;
}

export type JiraStatus =
  | { state: "ok"; project_key: string; issues: JiraIssue[]; truncated: boolean }
  | { state: "not_linked" }
  | { state: "not_connected" }
  | { state: "error"; message: string };

export interface GithubItem {
  number: number;
  title: string;
  url: string;
}

export type GithubStatus =
  | { state: "ok"; repo: string; pull_requests: GithubItem[]; issues: GithubItem[] }
  | { state: "not_linked" }
  | { state: "not_connected" }
  | { state: "error"; message: string };

export async function getJiraStatus(idToken: string, tenantId: string): Promise<JiraStatus> {
  const res = await fetch(`${API_BASE}/tenants/${encodeURIComponent(tenantId)}/jira_status`, {
    headers: { Authorization: `Bearer ${idToken}` },
  });
  if (!res.ok) throw new Error(`getJiraStatus failed: ${res.status}`);
  return res.json();
}

export async function getGithubStatus(idToken: string, tenantId: string): Promise<GithubStatus> {
  const res = await fetch(`${API_BASE}/tenants/${encodeURIComponent(tenantId)}/github_status`, {
    headers: { Authorization: `Bearer ${idToken}` },
  });
  if (!res.ok) throw new Error(`getGithubStatus failed: ${res.status}`);
  return res.json();
}
