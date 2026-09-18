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

export async function listTenants(ownerUid: string): Promise<Tenant[]> {
  const res = await fetch(`${API_BASE}/tenants`, {
    headers: { "X-Owner-Uid": ownerUid },
  });
  if (!res.ok) throw new Error(`listTenants failed: ${res.status}`);
  return res.json();
}

export async function getTenantFacts(ownerUid: string, tenantId: string): Promise<Fact[]> {
  const res = await fetch(`${API_BASE}/tenants/${tenantId}/facts`, {
    headers: { "X-Owner-Uid": ownerUid },
  });
  if (!res.ok) throw new Error(`getTenantFacts failed: ${res.status}`);
  return res.json();
}

export function chatSocketUrl(ownerUid: string, tenantId: string): string {
  const base = API_BASE.replace("http", "ws");
  return `${base}/ws/chat/${tenantId}?owner_uid=${encodeURIComponent(ownerUid)}`;
}
