import { API_BASE, ForbiddenError } from "./client";

export interface Tenant {
  tenant_id: string;
  name: string;
  jira_project_key: string | null;
  // "owner/name" of the linked GitHub repo, or null.
  github_repo: string | null;
}

export async function listTenants(idToken: string): Promise<Tenant[]> {
  const res = await fetch(`${API_BASE}/tenants`, {
    headers: { Authorization: `Bearer ${idToken}` },
  });
  if (res.status === 403) throw new ForbiddenError("This account isn't allowed to use Anamnesis.");
  if (!res.ok) throw new Error(`listTenants failed: ${res.status}`);
  return res.json();
}

// The name's project id is taken (by anyone) — the message says what to do.
export class NameTakenError extends Error {}

export async function createTenant(idToken: string, name: string): Promise<{ tenant_id: string }> {
  const res = await fetch(`${API_BASE}/tenants`, {
    method: "POST",
    headers: { Authorization: `Bearer ${idToken}`, "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (res.status === 409) {
    const detail = (await res.json().catch(() => null))?.detail;
    throw new NameTakenError(detail || "That project name isn't available. Try another name.");
  }
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

// Which GitHub repo / Jira project a project is linked to. A
// value links or changes it, null unlinks it. A 400 carries the reason the
// value was refused (not an owner/name repo, not a Jira key ...) — surface it.
export async function setTenantLink(
  idToken: string,
  tenantId: string,
  field: "github_repo" | "jira_project_key",
  value: string | null,
): Promise<void> {
  const res = await fetch(`${API_BASE}/tenants/${encodeURIComponent(tenantId)}/${field}`, {
    method: value === null ? "DELETE" : "PUT",
    headers: { Authorization: `Bearer ${idToken}`, "Content-Type": "application/json" },
    body: value === null ? undefined : JSON.stringify({ [field]: value }),
  });
  if (!res.ok) {
    const detail = res.status === 400 ? (await res.json().catch(() => null))?.detail : null;
    throw new Error(detail || `setTenantLink failed: ${res.status}`);
  }
}
