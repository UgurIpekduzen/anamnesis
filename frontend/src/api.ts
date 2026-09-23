// Points at the FastAPI backend's host-mapped port (see docker-compose.yml).
// Revisited in APPCE-56 once there's a real deployed backend origin.
const API_BASE = "http://localhost:8010";

export interface Tenant {
  tenant_id: string;
  name: string;
  jira_project_key: string | null;
  git_repo_path: string | null;
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

export async function getTenantFacts(idToken: string, tenantId: string): Promise<Fact[]> {
  const res = await fetch(`${API_BASE}/tenants/${tenantId}/facts`, {
    headers: { Authorization: `Bearer ${idToken}` },
  });
  if (!res.ok) throw new Error(`getTenantFacts failed: ${res.status}`);
  return res.json();
}

// No token in the URL: URLs end up in access logs. The socket authenticates
// with its first frame instead (see Chat.tsx and APPCE-67).
export function chatSocketUrl(tenantId: string): string {
  const base = API_BASE.replace("http", "ws");
  return `${base}/ws/chat/${tenantId}`;
}

export interface Usage {
  count: number;
  threshold: number;
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
