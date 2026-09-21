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

export function chatSocketUrl(idToken: string, tenantId: string): string {
  const base = API_BASE.replace("http", "ws");
  return `${base}/ws/chat/${tenantId}?token=${encodeURIComponent(idToken)}`;
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
