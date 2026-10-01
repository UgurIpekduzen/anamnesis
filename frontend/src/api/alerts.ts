import { API_BASE } from "./client";

// Whether a broken GitHub connection's poll failures reach the owner's
// inbox — owner-only, same as everything else in this file.
export interface AlertsState {
  github_poll_alert_muted: boolean;
}

export async function getAlerts(idToken: string): Promise<AlertsState> {
  const res = await fetch(`${API_BASE}/admin/alerts`, {
    headers: { Authorization: `Bearer ${idToken}` },
  });
  if (!res.ok) throw new Error(`getAlerts failed: ${res.status}`);
  return res.json();
}

export async function setAlerts(idToken: string, state: AlertsState): Promise<AlertsState> {
  const res = await fetch(`${API_BASE}/admin/alerts`, {
    method: "PUT",
    headers: { Authorization: `Bearer ${idToken}`, "Content-Type": "application/json" },
    body: JSON.stringify(state),
  });
  if (!res.ok) throw new Error(`setAlerts failed: ${res.status}`);
  return res.json();
}
