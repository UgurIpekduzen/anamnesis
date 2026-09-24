// In dev, the Vite dev server (this file) and the FastAPI backend run as
// separate processes on different ports (see docker-compose.yml), so calls
// need an absolute URL. In production the backend serves this same built
// frontend from one origin (APPCE-56), so relative paths (same origin,
// no CORS) are both simpler and correct.
const API_BASE = import.meta.env.DEV ? "http://localhost:8010" : "";

export interface Tenant {
  tenant_id: string;
  name: string;
  jira_project_key: string | null;
  git_repo_path: string | null;
  // "owner/name" of the linked GitHub repo (APPCE-83), or null.
  github_repo: string | null;
}

export interface Fact {
  fact_id: string;
  content: string;
  category: string;
  created_at: string;
}

export async function listTenants(idToken: string): Promise<Tenant[]> {
  const res = await fetch(`${API_BASE}/tenants`, {
    headers: { Authorization: `Bearer ${idToken}` },
  });
  if (!res.ok) throw new Error(`listTenants failed: ${res.status}`);
  return res.json();
}

export async function createTenant(idToken: string, name: string): Promise<{ tenant_id: string }> {
  const res = await fetch(`${API_BASE}/tenants`, {
    method: "POST",
    headers: { Authorization: `Bearer ${idToken}`, "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!res.ok) throw new Error(`createTenant failed: ${res.status}`);
  return res.json();
}

export async function renameTenant(idToken: string, tenantId: string, name: string): Promise<void> {
  const res = await fetch(`${API_BASE}/tenants/${tenantId}`, {
    method: "PATCH",
    headers: { Authorization: `Bearer ${idToken}`, "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!res.ok) throw new Error(`renameTenant failed: ${res.status}`);
}

export async function deleteTenant(idToken: string, tenantId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/tenants/${tenantId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${idToken}` },
  });
  if (!res.ok) throw new Error(`deleteTenant failed: ${res.status}`);
}

export async function getTenantFacts(idToken: string, tenantId: string): Promise<Fact[]> {
  const res = await fetch(`${API_BASE}/tenants/${tenantId}/facts`, {
    headers: { Authorization: `Bearer ${idToken}` },
  });
  if (!res.ok) throw new Error(`getTenantFacts failed: ${res.status}`);
  return res.json();
}

export interface PendingFact {
  pending_fact_id: string;
  content: string;
  category: string;
  source: string;
  source_url: string;
  created_at: string;
}

export async function getPendingFacts(idToken: string, tenantId: string): Promise<PendingFact[]> {
  const res = await fetch(`${API_BASE}/tenants/${tenantId}/pending_facts`, {
    headers: { Authorization: `Bearer ${idToken}` },
  });
  if (!res.ok) throw new Error(`getPendingFacts failed: ${res.status}`);
  return res.json();
}

export async function approvePendingFact(idToken: string, tenantId: string, pendingFactId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/tenants/${tenantId}/pending_facts/${pendingFactId}/approve`, {
    method: "POST",
    headers: { Authorization: `Bearer ${idToken}` },
  });
  if (!res.ok) throw new Error(`approvePendingFact failed: ${res.status}`);
}

export async function rejectPendingFact(idToken: string, tenantId: string, pendingFactId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/tenants/${tenantId}/pending_facts/${pendingFactId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${idToken}` },
  });
  if (!res.ok) throw new Error(`rejectPendingFact failed: ${res.status}`);
}

// No token in the URL: URLs end up in access logs. The socket authenticates
// with its first frame instead (see Chat.tsx and APPCE-67).
export function chatSocketUrl(tenantId: string): string {
  // API_BASE is relative in production (see above), so there's no origin
  // to turn into a ws(s):// URL — build one from the page's own instead.
  const wsBase = API_BASE
    ? API_BASE.replace(/^http/, "ws")
    : `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}`;
  return `${wsBase}/ws/chat/${tenantId}`;
}

export interface Usage {
  count: number;
  // Soft warning the user sets themselves; nothing is blocked at it.
  threshold: number;
  // Hard daily ceiling: messages past it are refused (APPCE-102).
  limit: number;
  // ISO timestamp of the next midnight UTC, when the count starts over.
  resets_at: string;
}

export async function getUsage(idToken: string): Promise<Usage> {
  const res = await fetch(`${API_BASE}/usage`, {
    headers: { Authorization: `Bearer ${idToken}` },
  });
  if (!res.ok) throw new Error(`getUsage failed: ${res.status}`);
  return res.json();
}

export interface SettingsValues {
  history_turns: number;
  daily_message_warning_threshold: number;
}

export interface SettingsResponse extends SettingsValues {
  // Served by the backend so the form's min/max never drifts from what
  // the server actually enforces.
  limits: Record<keyof SettingsValues, { min: number; max: number }>;
  // What "Reset to defaults" goes back to.
  defaults: SettingsValues;
}

export async function getSettings(idToken: string): Promise<SettingsResponse> {
  const res = await fetch(`${API_BASE}/settings`, {
    headers: { Authorization: `Bearer ${idToken}` },
  });
  if (!res.ok) throw new Error(`getSettings failed: ${res.status}`);
  return res.json();
}

export async function updateSettings(idToken: string, values: SettingsValues): Promise<SettingsResponse> {
  const res = await fetch(`${API_BASE}/settings`, {
    method: "PUT",
    headers: { Authorization: `Bearer ${idToken}`, "Content-Type": "application/json" },
    body: JSON.stringify(values),
  });
  if (!res.ok) throw new Error(`updateSettings failed: ${res.status}`);
  return res.json();
}

export async function resetSettings(idToken: string): Promise<SettingsResponse> {
  const res = await fetch(`${API_BASE}/settings`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${idToken}` },
  });
  if (!res.ok) throw new Error(`resetSettings failed: ${res.status}`);
  return res.json();
}

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

export interface SavedTurn {
  question: string;
  answer: string;
  created_at: string;
}

export async function getChatHistory(idToken: string, tenantId: string): Promise<SavedTurn[]> {
  const res = await fetch(`${API_BASE}/tenants/${tenantId}/history`, {
    headers: { Authorization: `Bearer ${idToken}` },
  });
  if (!res.ok) throw new Error(`getChatHistory failed: ${res.status}`);
  return res.json();
}

export interface AllowedEmails {
  owner_emails: string[];
  extra_emails: string[];
}

// A 403 here means the signed-in user isn't an owner — expected for
// everyone but the Terraform-configured owner(s), not an error the caller
// needs to report (APPCE-94). Callers use this to decide whether to show
// the admin section at all, so null (not a thrown error) means "hidden".
export async function getAllowedEmails(idToken: string): Promise<AllowedEmails | null> {
  const res = await fetch(`${API_BASE}/admin/allowed_emails`, {
    headers: { Authorization: `Bearer ${idToken}` },
  });
  if (res.status === 403) return null;
  if (!res.ok) throw new Error(`getAllowedEmails failed: ${res.status}`);
  return res.json();
}

export async function addAllowedEmail(idToken: string, email: string): Promise<{ extra_emails: string[] }> {
  const res = await fetch(`${API_BASE}/admin/allowed_emails`, {
    method: "POST",
    headers: { Authorization: `Bearer ${idToken}`, "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  if (!res.ok) {
    const detail = res.status === 400 ? (await res.json().catch(() => null))?.detail : null;
    throw new Error(detail || `addAllowedEmail failed: ${res.status}`);
  }
  return res.json();
}

export async function removeAllowedEmail(idToken: string, email: string): Promise<{ extra_emails: string[] }> {
  const res = await fetch(`${API_BASE}/admin/allowed_emails/${encodeURIComponent(email)}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${idToken}` },
  });
  if (!res.ok) throw new Error(`removeAllowedEmail failed: ${res.status}`);
  return res.json();
}
