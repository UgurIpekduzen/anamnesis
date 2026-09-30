import { API_BASE } from "./client";

// Owner-only admin calls: who may sign in, their role, and shared settings.

// "admin" is the owner (from Terraform), never settable here. An invited
// email is "user" (exempt from the tester lifetime message cap)
// or "tester" (the default).
export type Role = "user" | "tester";

export interface AllowedEmails {
  owner_emails: string[];
  extra_users: { email: string; role: Role }[];
}

// A 403 here means the signed-in user isn't an owner — expected for
// everyone but the Terraform-configured owner(s), not an error the caller
// needs to report. Callers use this to decide whether to show
// the admin section at all, so null (not a thrown error) means "hidden".
export async function getAllowedEmails(idToken: string): Promise<AllowedEmails | null> {
  const res = await fetch(`${API_BASE}/admin/allowed_emails`, {
    headers: { Authorization: `Bearer ${idToken}` },
  });
  if (res.status === 403) return null;
  if (!res.ok) throw new Error(`getAllowedEmails failed: ${res.status}`);
  return res.json();
}

export async function addAllowedEmail(
  idToken: string,
  email: string,
): Promise<{ extra_users: AllowedEmails["extra_users"] }> {
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

export async function removeAllowedEmail(
  idToken: string,
  email: string,
): Promise<{ extra_users: AllowedEmails["extra_users"] }> {
  const res = await fetch(`${API_BASE}/admin/allowed_emails/${encodeURIComponent(email)}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${idToken}` },
  });
  if (!res.ok) throw new Error(`removeAllowedEmail failed: ${res.status}`);
  return res.json();
}

export async function setRole(
  idToken: string,
  email: string,
  role: Role,
): Promise<{ extra_users: AllowedEmails["extra_users"] }> {
  const res = await fetch(`${API_BASE}/admin/allowed_emails/${encodeURIComponent(email)}/role`, {
    method: "PUT",
    headers: { Authorization: `Bearer ${idToken}`, "Content-Type": "application/json" },
    body: JSON.stringify({ role }),
  });
  if (!res.ok) {
    const detail = res.status === 400 ? (await res.json().catch(() => null))?.detail : null;
    throw new Error(detail || `setRole failed: ${res.status}`);
  }
  return res.json();
}

// Permanently deletes email's data (projects, connections, usage,
// preferences) and their allowlist entry — not just access removal
// confirmEmail must repeat email exactly; the backend refuses
// otherwise, the same retype-to-confirm friction as removing a project.
export async function wipeUser(
  idToken: string,
  email: string,
  confirmEmail: string,
): Promise<{ extra_users: AllowedEmails["extra_users"] }> {
  const res = await fetch(`${API_BASE}/admin/users/${encodeURIComponent(email)}/wipe`, {
    method: "POST",
    headers: { Authorization: `Bearer ${idToken}`, "Content-Type": "application/json" },
    body: JSON.stringify({ confirm_email: confirmEmail }),
  });
  if (!res.ok) {
    const detail = res.status === 400 ? (await res.json().catch(() => null))?.detail : null;
    throw new Error(detail || `wipeUser failed: ${res.status}`);
  }
  return res.json();
}

// history_turns and daily_message_warning_threshold used to be each user's
// own setting; they were moved here as one shared value for everyone
// (owner-only) — history_turns is a cost lever, the same kind of knob as
// the daily/global message limits, not a per-user preference.
export interface SharedSettingsValues {
  history_turns: number;
  daily_message_warning_threshold: number;
}

export interface SharedSettingsResponse extends SharedSettingsValues {
  limits: Record<keyof SharedSettingsValues, { min: number; max: number }>;
  defaults: SharedSettingsValues;
}

export async function getSharedSettings(idToken: string): Promise<SharedSettingsResponse> {
  const res = await fetch(`${API_BASE}/admin/settings`, {
    headers: { Authorization: `Bearer ${idToken}` },
  });
  if (!res.ok) throw new Error(`getSharedSettings failed: ${res.status}`);
  return res.json();
}

export async function setSharedSettings(
  idToken: string,
  values: SharedSettingsValues,
): Promise<SharedSettingsResponse> {
  const res = await fetch(`${API_BASE}/admin/settings`, {
    method: "PUT",
    headers: { Authorization: `Bearer ${idToken}`, "Content-Type": "application/json" },
    body: JSON.stringify(values),
  });
  if (!res.ok) {
    const detail = res.status === 400 ? (await res.json().catch(() => null))?.detail : null;
    throw new Error(detail || `setSharedSettings failed: ${res.status}`);
  }
  return res.json();
}

// One row per allowed email — merges what getAllowedEmails/getAdminUsage
// each separately expose, plus the display name the owner can set
// searchable and pageable server-side.
export interface AdminUserRow {
  email: string;
  role: Role | "admin";
  name: string | null;
  count: number;
  // ISO 8601, or null for the owner (they come from Terraform, not this
  // invite flow) — when this email was added to the allowlist.
  invited_at: string | null;
}

export interface AdminUsersPage {
  users: AdminUserRow[];
  total: number;
  limit: number;
  offset: number;
  global: { count: number; limit: number };
}

export async function listUsers(
  idToken: string,
  { q = "", limit = 200, offset = 0 }: { q?: string; limit?: number; offset?: number } = {},
): Promise<AdminUsersPage> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (q) params.set("q", q);
  const res = await fetch(`${API_BASE}/admin/users?${params}`, {
    headers: { Authorization: `Bearer ${idToken}` },
  });
  if (!res.ok) throw new Error(`listUsers failed: ${res.status}`);
  return res.json();
}

// A label the owner chooses for an email — never captured from the user's
// own Google account. An empty string clears a name set by mistake.
export async function setUserName(
  idToken: string,
  email: string,
  name: string,
): Promise<{ name: string | null }> {
  const res = await fetch(`${API_BASE}/admin/users/${encodeURIComponent(email)}/name`, {
    method: "PUT",
    headers: { Authorization: `Bearer ${idToken}`, "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!res.ok) {
    const detail = res.status === 400 ? (await res.json().catch(() => null))?.detail : null;
    throw new Error(detail || `setUserName failed: ${res.status}`);
  }
  return res.json();
}
