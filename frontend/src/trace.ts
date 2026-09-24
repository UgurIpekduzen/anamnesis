// What the Chat emits as a conversation turn plays out. Kept free of React
// so the reducer below is plain, checkable logic.
export type ChatEvent =
  | { type: "sent"; question: string }
  | { type: "tool_call"; id?: string | null; name: string; args: unknown }
  | { type: "tool_result"; id?: string | null; name: string; result: unknown }
  | { type: "answered" }
  | { type: "failed" }
  | { type: "cleared" };

export interface TraceCall {
  id?: string | null;
  name: string;
  args: unknown;
  startedAt: number;
  result?: unknown;
  durationMs?: number;
}

export interface TraceTurn {
  question: string;
  startedAt: number;
  calls: TraceCall[];
  status: "running" | "done" | "failed";
  durationMs?: number;
}

// The timestamp rides on the action (rather than the reducer calling
// Date.now()) so the reducer stays pure.
export type TraceAction = ChatEvent & { at: number };

// Old turns only matter for a quick look back; this keeps memory bounded
// in a long session.
const MAX_TURNS = 20;

function updateLastTurn(turns: TraceTurn[], update: (turn: TraceTurn) => TraceTurn): TraceTurn[] {
  if (turns.length === 0) return turns;
  return [...turns.slice(0, -1), update(turns[turns.length - 1])];
}

function resolveCall(calls: TraceCall[], id: string | null | undefined, name: string): number {
  // Prefer the id: a model can call the same tool twice in one turn, and
  // pairing by name alone would attach a result to the wrong call.
  if (id) {
    const byId = calls.findIndex((call) => call.id === id && call.result === undefined);
    if (byId !== -1) return byId;
  }
  for (let i = calls.length - 1; i >= 0; i--) {
    if (calls[i].name === name && calls[i].result === undefined) return i;
  }
  return -1;
}

export function traceReducer(turns: TraceTurn[], action: TraceAction): TraceTurn[] {
  switch (action.type) {
    case "sent":
      return [
        ...turns,
        { question: action.question, startedAt: action.at, calls: [], status: "running" as const },
      ].slice(-MAX_TURNS);

    case "tool_call":
      return updateLastTurn(turns, (turn) => ({
        ...turn,
        calls: [...turn.calls, { id: action.id, name: action.name, args: action.args, startedAt: action.at }],
      }));

    case "tool_result":
      return updateLastTurn(turns, (turn) => {
        const index = resolveCall(turn.calls, action.id, action.name);
        if (index === -1) return turn;
        const calls = turn.calls.map((call, i) =>
          i === index ? { ...call, result: action.result, durationMs: action.at - call.startedAt } : call,
        );
        return { ...turn, calls };
      });

    case "answered":
    case "failed":
      return updateLastTurn(turns, (turn) => ({
        ...turn,
        status: action.type === "answered" ? "done" : "failed",
        durationMs: action.at - turn.startedAt,
      }));

    case "cleared":
      return [];
  }
}
