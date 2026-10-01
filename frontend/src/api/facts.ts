import { API_BASE } from "./client";

// Two distinct concepts live here: approved facts (Fact, already part of a
// project's remembered context) and pending facts (PendingFact, candidates
// staged for the owner to review before they become real facts).
export interface Fact {
  fact_id: string;
  content: string;
  category: string;
  created_at: string;
}

export async function getTenantFacts(idToken: string, tenantId: string): Promise<Fact[]> {
  const res = await fetch(`${API_BASE}/tenants/${tenantId}/facts`, {
    headers: { Authorization: `Bearer ${idToken}` },
  });
  if (!res.ok) throw new Error(`getTenantFacts failed: ${res.status}`);
  return res.json();
}

// What a chat proposal card's button calls. A 400 carries the
// reason (e.g. an unknown category) — surface it.
export async function updateFact(
  idToken: string,
  tenantId: string,
  factId: string,
  changes: { content?: string; category?: string },
): Promise<void> {
  const res = await fetch(
    `${API_BASE}/tenants/${encodeURIComponent(tenantId)}/facts/${encodeURIComponent(factId)}`,
    {
      method: "PATCH",
      headers: { Authorization: `Bearer ${idToken}`, "Content-Type": "application/json" },
      body: JSON.stringify(changes),
    },
  );
  if (!res.ok) {
    const detail = res.status === 400 ? (await res.json().catch(() => null))?.detail : null;
    throw new Error(detail || `updateFact failed: ${res.status}`);
  }
}

export async function deleteFact(idToken: string, tenantId: string, factId: string): Promise<void> {
  const res = await fetch(
    `${API_BASE}/tenants/${encodeURIComponent(tenantId)}/facts/${encodeURIComponent(factId)}`,
    {
      method: "DELETE",
      headers: { Authorization: `Bearer ${idToken}` },
    },
  );
  if (!res.ok) throw new Error(`deleteFact failed: ${res.status}`);
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

// How the staged facts were decided; the approval rate is
// approved / (approved + rejected).
export interface PendingFactStats {
  pending: number;
  approved: number;
  rejected: number;
}

export async function getPendingFactStats(
  idToken: string,
  tenantId: string,
): Promise<PendingFactStats> {
  const res = await fetch(`${API_BASE}/tenants/${tenantId}/pending_facts/stats`, {
    headers: { Authorization: `Bearer ${idToken}` },
  });
  if (!res.ok) throw new Error(`getPendingFactStats failed: ${res.status}`);
  return res.json();
}

export async function approvePendingFact(
  idToken: string,
  tenantId: string,
  pendingFactId: string,
): Promise<void> {
  const res = await fetch(
    `${API_BASE}/tenants/${tenantId}/pending_facts/${pendingFactId}/approve`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${idToken}` },
    },
  );
  if (!res.ok) throw new Error(`approvePendingFact failed: ${res.status}`);
}

export async function rejectPendingFact(
  idToken: string,
  tenantId: string,
  pendingFactId: string,
): Promise<void> {
  const res = await fetch(`${API_BASE}/tenants/${tenantId}/pending_facts/${pendingFactId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${idToken}` },
  });
  if (!res.ok) throw new Error(`rejectPendingFact failed: ${res.status}`);
}
