import { API_BASE } from "./client";

export interface CategorySettings {
  categories: string[];
  // What "Reset to suggested" goes back to, and what can be added back.
  suggested: string[];
  customized: boolean;
  max: number;
}

export async function getCategories(idToken: string): Promise<CategorySettings> {
  const res = await fetch(`${API_BASE}/categories`, {
    headers: { Authorization: `Bearer ${idToken}` },
  });
  if (!res.ok) throw new Error(`getCategories failed: ${res.status}`);
  return res.json();
}

export async function saveCategories(
  idToken: string,
  categories: string[],
): Promise<CategorySettings> {
  const res = await fetch(`${API_BASE}/categories`, {
    method: "PUT",
    headers: { Authorization: `Bearer ${idToken}`, "Content-Type": "application/json" },
    body: JSON.stringify({ categories }),
  });
  if (!res.ok) {
    // A 400 says which rule the list broke — show it instead of a generic failure.
    const detail = res.status === 400 ? (await res.json().catch(() => null))?.detail : null;
    throw new Error(detail || `saveCategories failed: ${res.status}`);
  }
  return res.json();
}

export async function resetCategories(idToken: string): Promise<CategorySettings> {
  const res = await fetch(`${API_BASE}/categories`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${idToken}` },
  });
  if (!res.ok) throw new Error(`resetCategories failed: ${res.status}`);
  return res.json();
}
