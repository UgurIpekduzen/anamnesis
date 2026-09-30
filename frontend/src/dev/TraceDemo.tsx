import { useEffect, useReducer, useRef, useState } from "react";

import "../App.css";
import TracePanel from "../components/TracePanel";
import { traceReducer, type TraceAction, type TraceTurn } from "../trace";
import { FIXTURE_TURNS, LIVE_TURN_STEPS, fillerTurns } from "./traceFixtures";

// Dev-only: the real Trace panel in the real sidebar styles,
// filled from static data. No sign-in, no API, no model calls.
type DemoAction =
  | TraceAction
  | { type: "replace"; turns: TraceTurn[]; at: number }
  | { type: "append"; turns: TraceTurn[]; at: number };

function demoReducer(turns: TraceTurn[], action: DemoAction): TraceTurn[] {
  if (action.type === "replace") return action.turns;
  if (action.type === "append") return [...turns, ...action.turns];
  return traceReducer(turns, action);
}

function TraceDemo() {
  const [turns, dispatch] = useReducer(demoReducer, FIXTURE_TURNS);
  const [width, setWidth] = useState(360);
  const [fillerCount, setFillerCount] = useState(0);
  const timers = useRef<number[]>([]);

  useEffect(() => () => timers.current.forEach(clearTimeout), []);

  function replayLiveTurn() {
    let elapsed = 0;
    for (const step of LIVE_TURN_STEPS) {
      elapsed += step.delayMs;
      timers.current.push(
        window.setTimeout(() => dispatch({ ...step.event, at: Date.now() }), elapsed),
      );
    }
  }

  function addFiller() {
    dispatch({ type: "append", turns: fillerTurns(5, fillerCount + 1), at: 0 });
    setFillerCount((n) => n + 5);
  }

  return (
    <div className="app">
      <aside className="sidebar" style={{ width }}>
        <div className="tabs">
          <button className="tab">Facts</button>
          <button className="tab active">
            Trace
            {turns.length > 0 && <span className="tab-badge">{turns.length}</span>}
          </button>
        </div>
        <div className="sidebar-panel">
          <TracePanel turns={turns} />
        </div>
      </aside>

      <main className="main">
        <div className="main-inner" style={{ gap: 16 }}>
          <h1>Trace demo</h1>
          <p style={{ color: "var(--text-muted)" }}>
            Static data through the real reducer and panel (dev only). Nothing here calls the API or
            the model.
          </p>

          <label>
            Sidebar width: {width}px
            <input
              type="range"
              min={200}
              max={Math.max(400, window.innerWidth - 320)}
              value={width}
              onChange={(e) => setWidth(Number(e.target.value))}
              style={{ width: "100%" }}
            />
          </label>

          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button onClick={() => dispatch({ type: "replace", turns: FIXTURE_TURNS, at: 0 })}>
              Load fixtures
            </button>
            <button onClick={replayLiveTurn}>Replay a live turn (~4.5 s)</button>
            <button onClick={addFiller}>Add 5 filler turns</button>
            <button onClick={() => dispatch({ type: "cleared", at: Date.now() })}>Clear</button>
          </div>

          <ul
            style={{ color: "var(--text-muted)", fontSize: 14, lineHeight: 1.6, paddingLeft: 18 }}
          >
            <li>Newest turn on top and open; older turns are collapsed.</li>
            <li>
              Turns cover: no tools, long table with timestamps, scalar result, same tool twice,
              nested args, error, failed, running.
            </li>
            <li>
              Check scrolling with the filler turns, and the 20-turn cap by adding more than 20.
            </li>
          </ul>
        </div>
      </main>
    </div>
  );
}

export default TraceDemo;
