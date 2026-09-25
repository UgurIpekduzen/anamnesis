import { API_BASE } from "./client";

export interface GithubConnection {
  connected: boolean;
}

export async function getGithubConnection(idToken: string): Promise<GithubConnection> {
  const res = await fetch(`${API_BASE}/github/connection`, {
    headers: { Authorization: `Bearer ${idToken}` },
  });
  if (!res.ok) throw new Error(`getGithubConnection failed: ${res.status}`);
  return res.json();
}

export async function connectGithub(idToken: string, token: string): Promise<GithubConnection> {
  const res = await fetch(`${API_BASE}/github/connection`, {
    method: "PUT",
    headers: { Authorization: `Bearer ${idToken}`, "Content-Type": "application/json" },
    body: JSON.stringify({ token }),
  });
  if (!res.ok) {
    // A 400 carries a reason the user can act on (wrong token kind,
    // expired, ...) — surface it instead of a generic failure message.
    const detail = res.status === 400 ? (await res.json().catch(() => null))?.detail : null;
    throw new Error(detail || `connectGithub failed: ${res.status}`);
  }
  return res.json();
}

export async function disconnectGithub(idToken: string): Promise<GithubConnection> {
  const res = await fetch(`${API_BASE}/github/connection`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${idToken}` },
  });
  if (!res.ok) throw new Error(`disconnectGithub failed: ${res.status}`);
  return res.json();
}

export interface JiraConnection {
  connected: boolean;
  // The workspace address, only sent by GET while connected (APPCE-105);
  // it lets the UI link a project's Jira key.
  base_url?: string | null;
}

export async function getJiraConnection(idToken: string): Promise<JiraConnection> {
  const res = await fetch(`${API_BASE}/jira/connection`, {
    headers: { Authorization: `Bearer ${idToken}` },
  });
  if (!res.ok) throw new Error(`getJiraConnection failed: ${res.status}`);
  return res.json();
}

export async function connectJira(
  idToken: string,
  email: string,
  token: string,
  baseUrl: string,
): Promise<JiraConnection> {
  const res = await fetch(`${API_BASE}/jira/connection`, {
    method: "PUT",
    headers: { Authorization: `Bearer ${idToken}`, "Content-Type": "application/json" },
    body: JSON.stringify({ email, token, base_url: baseUrl }),
  });
  if (!res.ok) {
    // A 400 carries a reason the user can act on (wrong credentials,
    // unreachable workspace, ...) — surface it instead of a generic
    // failure message.
    const detail = res.status === 400 ? (await res.json().catch(() => null))?.detail : null;
    throw new Error(detail || `connectJira failed: ${res.status}`);
  }
  return res.json();
}

export async function disconnectJira(idToken: string): Promise<JiraConnection> {
  const res = await fetch(`${API_BASE}/jira/connection`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${idToken}` },
  });
  if (!res.ok) throw new Error(`disconnectJira failed: ${res.status}`);
  return res.json();
}
