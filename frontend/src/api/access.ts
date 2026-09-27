import { API_BASE } from "./client";

export interface AllowedEmails {
  owner_emails: string[];
  extra_emails: string[];
  // Extra emails exempt from the tester lifetime message cap (APPCE-122).
  unlimited_emails: string[];
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

export async function markUnlimited(idToken: string, email: string): Promise<{ unlimited_emails: string[] }> {
  const res = await fetch(`${API_BASE}/admin/allowed_emails/${encodeURIComponent(email)}/unlimited`, {
    method: "POST",
    headers: { Authorization: `Bearer ${idToken}` },
  });
  if (!res.ok) {
    const detail = res.status === 400 ? (await res.json().catch(() => null))?.detail : null;
    throw new Error(detail || `markUnlimited failed: ${res.status}`);
  }
  return res.json();
}

export async function unmarkUnlimited(idToken: string, email: string): Promise<{ unlimited_emails: string[] }> {
  const res = await fetch(`${API_BASE}/admin/allowed_emails/${encodeURIComponent(email)}/unlimited`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${idToken}` },
  });
  if (!res.ok) throw new Error(`unmarkUnlimited failed: ${res.status}`);
  return res.json();
}

export interface AdminUsage {
  users: { email: string; count: number }[];
  // A ceiling across every user combined, on top of each user's own
  // (APPCE-122) — this is that shared count and its limit.
  global: { count: number; limit: number };
}

export async function getAdminUsage(idToken: string): Promise<AdminUsage> {
  const res = await fetch(`${API_BASE}/admin/usage`, {
    headers: { Authorization: `Bearer ${idToken}` },
  });
  if (!res.ok) throw new Error(`getAdminUsage failed: ${res.status}`);
  return res.json();
}
