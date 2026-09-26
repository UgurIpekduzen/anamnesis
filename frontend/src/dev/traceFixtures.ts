// Static data for the dev-only Trace demo page (APPCE-75). Every scenario
// goes through the real traceReducer, so the demo shows exactly what a live
// conversation would produce, without signing in or spending a model call.
import { traceReducer, type ChatEvent, type TraceTurn } from "../trace";

// One step of a scripted turn: an event, and how many ms after the turn
// started it happens (which becomes the call/turn duration).
type Step = [afterMs: number, event: ChatEvent];

function play(question: string, startedAt: number, steps: Step[]): TraceTurn {
  let turns: TraceTurn[] = traceReducer([], { type: "sent", question, at: startedAt });
  for (const [afterMs, event] of steps) {
    turns = traceReducer(turns, { ...event, at: startedAt + afterMs });
  }
  return turns[0];
}

const TENANTS = [
  { tenant_id: "demo_app", name: "Demo App", jira_project_key: "DAPP" },
  { tenant_id: "demo_shop", name: "Demo Shop", jira_project_key: "SHOP" },
  { tenant_id: "demo_hiring", name: "Demo Hiring", jira_project_key: "HIRE" },
  { tenant_id: "demo_tool", name: "Demo Tool", jira_project_key: "TOOL" },
  { tenant_id: "demo_model", name: "Demo Model", jira_project_key: "MODEL" },
];

const FACT_TEXTS = [
  "frontend için React kullanılacak",
  "Backend için FastAPI kullanılacak",
  "deployment için push-based subscriber kullanılacak",
  "CI için GitHub Actions kullanılacak",
  "authentication için Firebase Auth kullanmaya karar verildi",
  "Kimlik doğrulama için Google Sign-In kullanılıyor; token Cloud Run üzerinde doğrulanacak, izin listesi uygulama tarafında tutulacak",
  "42 commits in the last 90 days.",
  "Auth JWT ile refresh token kullanıyor.",
];

// Same shape the API sends: fact_id, content, category, created_at as an
// ISO-8601 string with microseconds and a UTC offset.
const FACTS = Array.from({ length: 14 }, (_, i) => ({
  fact_id: `QuJ8tWooz4xfMkQSnbIf${String(i).padStart(2, "0")}`,
  content: FACT_TEXTS[i % FACT_TEXTS.length],
  category: ["architecture", "decision", "status", "bug", "todo"][i % 5],
  created_at: `2026-09-13T01:18:${String(10 + i).padStart(2, "0")}.963479+00:00`,
}));

const T0 = Date.parse("2026-09-22T10:00:00Z");

export const FIXTURE_TURNS: TraceTurn[] = [
  play("Merhaba", T0, [[3800, { type: "answered" }]]),

  play("Bu projedeki kararları listele.", T0 + 60_000, [
    [50, { type: "tool_call", id: "a1", name: "list_tenants", args: {} }],
    [313, { type: "tool_result", id: "a1", name: "list_tenants", result: { result: TENANTS } }],
    [900, { type: "tool_call", id: "a2", name: "get_tenant_facts", args: { tenant_id: "demo_app" } }],
    [1494, { type: "tool_result", id: "a2", name: "get_tenant_facts", result: { result: FACTS } }],
    [5300, { type: "answered" }],
  ]),

  play("Şu kararı kaydet: deployment Cloud Run'a yapılacak", T0 + 120_000, [
    [40, { type: "tool_call", id: "b1", name: "add_fact", args: { tenant_id: "demo_app", category: "decision", content: "deployment Cloud Run'a yapılacak" } }],
    [700, { type: "tool_result", id: "b1", name: "add_fact", result: { result: "3f9a1c7e5b2d4a688e0f" } }],
    [2400, { type: "answered" }],
  ]),

  // Same tool twice, results arriving in the opposite order: pairing must
  // follow the call id, not the tool name.
  play("İki projenin kararlarını karşılaştır.", T0 + 180_000, [
    [30, { type: "tool_call", id: "c1", name: "get_tenant_facts", args: { tenant_id: "demo_app" } }],
    [35, { type: "tool_call", id: "c2", name: "get_tenant_facts", args: { tenant_id: "demo_shop" } }],
    [420, { type: "tool_result", id: "c2", name: "get_tenant_facts", result: { result: [] } }],
    [610, { type: "tool_result", id: "c1", name: "get_tenant_facts", result: { result: FACTS.slice(0, 3) } }],
    [4100, { type: "answered" }],
  ]),

  play("Jira anahtarını güncelle.", T0 + 240_000, [
    [20, { type: "tool_call", id: "d1", name: "update_project", args: { tenant_id: "demo_app", settings: { jira_project_key: "DAPP", labels: ["a", "b"] } } }],
    [380, { type: "tool_result", id: "d1", name: "update_project", result: { result: { status: "ok", updated: ["jira_project_key"], at: "2026-09-22T10:04:00.123456+00:00" } } }],
    [1900, { type: "answered" }],
  ]),

  play("Jira'daki açık işleri getir.", T0 + 300_000, [
    [25, { type: "tool_call", id: "e1", name: "get_jira_status", args: { project_key: "DAPP" } }],
    [8200, { type: "tool_result", id: "e1", name: "get_jira_status", result: { error: "Jira request timed out after 8 s (HTTP 504)" } }],
    [8400, { type: "failed" }],
  ]),

  // Still running: the call has no result yet.
  play("Bu projede neler biliyorsun, detaylı özetle", T0 + 360_000, [
    [30, { type: "tool_call", id: "f1", name: "list_tenants", args: {} }],
  ]),
];

// A turn that plays out live, used by the "Replay a live turn" button: the
// delays are real, so the running state and the durations look genuine.
export const LIVE_TURN_STEPS: { delayMs: number; event: ChatEvent }[] = [
  { delayMs: 0, event: { type: "sent", question: "Canlı tur: bu projedeki kararları listele." } },
  { delayMs: 900, event: { type: "tool_call", id: "l1", name: "list_tenants", args: {} } },
  { delayMs: 300, event: { type: "tool_result", id: "l1", name: "list_tenants", result: { result: TENANTS } } },
  { delayMs: 1200, event: { type: "tool_call", id: "l2", name: "get_tenant_facts", args: { tenant_id: "demo_app" } } },
  { delayMs: 600, event: { type: "tool_result", id: "l2", name: "get_tenant_facts", result: { result: FACTS } } },
  { delayMs: 1500, event: { type: "answered" } },
];

// Filler turns to check scrolling and the 20-turn cap.
export function fillerTurns(count: number, from: number): TraceTurn[] {
  return Array.from({ length: count }, (_, i) =>
    play(`Dolgu sorusu #${from + i}`, T0 + 400_000 + i * 1_000, [
      [30, { type: "tool_call", id: `x${i}`, name: "get_tenant_facts", args: { tenant_id: "demo_app" } }],
      [500, { type: "tool_result", id: `x${i}`, name: "get_tenant_facts", result: { result: FACTS.slice(0, 5) } }],
      [1500, { type: "answered" }],
    ]),
  );
}
