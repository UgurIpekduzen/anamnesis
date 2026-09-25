import { API_BASE } from "./client";

export interface Usage {
  count: number;
  // Soft warning the user sets themselves; nothing is blocked at it.
  threshold: number;
  // Hard daily ceiling: messages past it are refused (APPCE-102).
  limit: number;
  // ISO timestamp of the next midnight UTC, when the count starts over.
  resets_at: string;
}

export async function getUsage(idToken: string): Promise<Usage> {
  const res = await fetch(`${API_BASE}/usage`, {
    headers: { Authorization: `Bearer ${idToken}` },
  });
  if (!res.ok) throw new Error(`getUsage failed: ${res.status}`);
  return res.json();
}
