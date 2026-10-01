// How a tool's arguments and result are shown in the Trace tab. Pure (no
// React) so the shape decisions are plain, checkable logic.

// The main ARGUMENTS/RESULT area never falls back to a raw JSON block — a
// nested value still fits a cell via cellText's JSON.stringify, so the
// worst case is a compact inline string, not a dedicated JSON view. The
// "Raw JSON" disclosure in TracePanel covers wanting the exact value.
export type ArgsView = { kind: "none" } | { kind: "table"; rows: [string, string][] };

export type ResultView =
  | { kind: "table"; columns: string[]; rows: string[][] }
  | { kind: "fields"; rows: [string, string][] }
  | { kind: "success"; detail?: string }
  | { kind: "error"; message: string }
  | { kind: "empty" };

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

// Matches the ISO-8601 timestamps the API sends (e.g. created_at), not an
// arbitrary string that happens to start with digits.
const ISO_DATETIME = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$/;

// Same formatting Facts.tsx uses for created_at, so a timestamp reads the
// same way whether it came through a tool result or the Facts list.
function formatIfTimestamp(value: string): string {
  if (!ISO_DATETIME.test(value)) return value;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function cellText(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") return formatIfTimestamp(value);
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function describeArgs(args: unknown): ArgsView {
  if (!isPlainObject(args) || Object.keys(args).length === 0) return { kind: "none" };
  return {
    kind: "table",
    rows: Object.entries(args).map(([name, value]) => [name, cellText(value)]),
  };
}

export function describeResult(response: unknown): ResultView {
  // ADK wraps a tool's return value as {"result": <value>}; a tool that
  // returns an error dict instead (e.g. {"error": "..."}) isn't wrapped,
  // so fall back to the raw response itself rather than a JSON block.
  const value = isPlainObject(response) && "result" in response ? response.result : response;

  if (value === null || value === undefined) return { kind: "success" };

  if (Array.isArray(value)) {
    if (value.length === 0) return { kind: "empty" };
    if (value.every(isPlainObject)) {
      // Union of keys in first-seen order, so a row missing a field
      // still lines up under the right column.
      const columns: string[] = [];
      for (const row of value) {
        for (const key of Object.keys(row)) if (!columns.includes(key)) columns.push(key);
      }
      return {
        kind: "table",
        columns,
        rows: value.map((row) => columns.map((column) => cellText(row[column]))),
      };
    }
    // A list of scalars (or a mixed list) doesn't fit the column-per-key
    // table above — one row per element instead of a JSON array.
    return { kind: "table", columns: ["value"], rows: value.map((item) => [cellText(item)]) };
  }

  if (isPlainObject(value)) {
    // A tool that failed returns {"error": "..."} instead of the usual
    // {"result": ...} wrapping — read the same way "Success" is, not as a
    // one-row table.
    if (Object.keys(value).length === 1 && typeof value.error === "string") {
      return { kind: "error", message: value.error };
    }

    const rows = Object.entries(value);
    if (rows.length === 0) return { kind: "empty" };
    // Reuses cellText for every field, nested or not, so e.g. a nested
    // object still renders (compactly, in that cell) instead of a JSON
    // block one level up.
    return { kind: "fields", rows: rows.map(([name, v]) => [name, cellText(v)]) };
  }

  // A single plain value is usually an opaque id (a published message id, a
  // tenant_id) rather than something meant to be read — lead with the
  // confirmation and keep the value secondary.
  return { kind: "success", detail: cellText(value) };
}
