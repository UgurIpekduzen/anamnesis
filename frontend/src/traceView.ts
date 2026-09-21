// How a tool's arguments and result are shown in the Trace tab. Pure (no
// React) so the shape decisions are plain, checkable logic. Mirrors what the
// Streamlit UI did in app/chat.py (_render_args / _render_result).

export type ArgsView =
  | { kind: "none" }
  | { kind: "table"; rows: [string, string][] }
  | { kind: "json"; text: string };

export type ResultView =
  | { kind: "table"; columns: string[]; rows: string[][] }
  | { kind: "success"; detail?: string }
  | { kind: "empty" }
  | { kind: "json"; text: string };

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function prettyJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2) ?? "undefined";
  } catch {
    return String(value);
  }
}

function cellText(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") return value;
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function describeArgs(args: unknown): ArgsView {
  if (!isPlainObject(args) || Object.keys(args).length === 0) return { kind: "none" };

  // A nested value doesn't fit a two-column table cell readably.
  const allFlat = Object.values(args).every((value) => value === null || typeof value !== "object");
  if (!allFlat) return { kind: "json", text: prettyJson(args) };

  return { kind: "table", rows: Object.entries(args).map(([name, value]) => [name, cellText(value)]) };
}

export function describeResult(response: unknown): ResultView {
  // ADK wraps a tool's return value as {"result": <value>}.
  if (isPlainObject(response) && "result" in response) {
    const value = response.result;

    if (Array.isArray(value)) {
      if (value.length === 0) return { kind: "empty" };
      if (value.every(isPlainObject)) {
        // Union of keys in first-seen order, so a row missing a field
        // still lines up under the right column.
        const columns: string[] = [];
        for (const row of value) {
          for (const key of Object.keys(row)) if (!columns.includes(key)) columns.push(key);
        }
        return { kind: "table", columns, rows: value.map((row) => columns.map((column) => cellText(row[column]))) };
      }
    } else if (value === null || value === undefined) {
      return { kind: "success" };
    } else if (typeof value !== "object") {
      // A single plain value is usually an opaque id (a published message
      // id, a tenant_id) rather than something meant to be read — lead with
      // the confirmation and keep the value secondary.
      return { kind: "success", detail: String(value) };
    }
  }
  return { kind: "json", text: prettyJson(response) };
}
