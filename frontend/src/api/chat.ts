import { API_BASE } from "./client";

// No token in the URL: URLs end up in access logs. The socket authenticates
// with its first frame instead (see Chat.tsx).
export function chatSocketUrl(tenantId: string): string {
  // API_BASE is relative in production (see above), so there's no origin
  // to turn into a ws(s):// URL — build one from the page's own instead.
  const wsBase = API_BASE
    ? API_BASE.replace(/^http/, "ws")
    : `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}`;
  return `${wsBase}/ws/chat/${tenantId}`;
}

interface SavedTurn {
  question: string;
  answer: string;
  created_at: string;
}

export async function getChatHistory(idToken: string, tenantId: string): Promise<SavedTurn[]> {
  const res = await fetch(`${API_BASE}/tenants/${tenantId}/history`, {
    headers: { Authorization: `Bearer ${idToken}` },
  });
  if (!res.ok) throw new Error(`getChatHistory failed: ${res.status}`);
  return res.json();
}
