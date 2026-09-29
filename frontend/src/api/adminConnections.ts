import { API_BASE } from "./client";

// A tenant whose last GitHub poll failed (APPCE-125) — owner-only, drops
// off the list on its own once a later poll succeeds.
export interface BrokenConnection {
  owner_uid: string;
  tenant_id: string;
  name: string | null;
  kind: "auth" | "not_found" | "other";
  failed_at: string | null;
}

export async function getBrokenConnections(idToken: string): Promise<BrokenConnection[]> {
  const res = await fetch(`${API_BASE}/admin/connections/broken`, {
    headers: { Authorization: `Bearer ${idToken}` },
  });
  if (!res.ok) throw new Error(`getBrokenConnections failed: ${res.status}`);
  const data = await res.json();
  return data.connections;
}
