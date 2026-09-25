import { API_BASE } from "./client";

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
