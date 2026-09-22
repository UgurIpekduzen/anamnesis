import type { TraceCall, TraceTurn } from "../trace";
import { describeArgs, describeResult, prettyJson } from "../traceView";
import "./TracePanel.css";

interface Props {
  turns: TraceTurn[];
}

function formatDuration(ms: number | undefined): string {
  if (ms === undefined) return "…";
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

const STATUS_GLYPH = { running: "⏳", done: "✓", failed: "✕" } as const;

function ArgsView({ args }: { args: unknown }) {
  const view = describeArgs(args);
  if (view.kind === "none") return <p className="trace-empty">No arguments</p>;
  return (
    <div className="trace-table-wrap">
      <table className="trace-table">
        <thead>
          <tr>
            <th>Argument</th>
            <th>Value</th>
          </tr>
        </thead>
        <tbody>
          {view.rows.map(([name, value]) => (
            <tr key={name}>
              <td>{name}</td>
              <td>{value}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ResultView({ result }: { result: unknown }) {
  const view = describeResult(result);
  if (view.kind === "empty") return <p className="trace-empty">Empty result</p>;
  if (view.kind === "success") {
    return (
      <p className="trace-success">
        ✅ Success
        {view.detail !== undefined && <small>{view.detail}</small>}
      </p>
    );
  }
  if (view.kind === "error") {
    return (
      <p className="trace-error">
        ❌ Error
        <small>{view.message}</small>
      </p>
    );
  }
  if (view.kind === "fields") {
    return (
      <div className="trace-table-wrap">
        <table className="trace-table">
          <tbody>
            {view.rows.map(([name, value]) => (
              <tr key={name}>
                <td>{name}</td>
                <td>{value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  return (
    <div className="trace-table-wrap">
      <table className="trace-table">
        <thead>
          <tr>
            {view.columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {view.rows.map((row, i) => (
            <tr key={i}>
              {row.map((cell, j) => (
                <td key={j}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CallView({ call }: { call: TraceCall }) {
  const pending = call.result === undefined;
  return (
    <details className="trace-call">
      <summary>
        <span className="trace-call-name">🔧 {call.name}</span>
        <small>{pending ? "running…" : formatDuration(call.durationMs)}</small>
      </summary>
      <div className="trace-section-label">Arguments</div>
      <ArgsView args={call.args} />
      <div className="trace-section-label">Result</div>
      {pending ? <p className="trace-empty">Waiting for the tool…</p> : <ResultView result={call.result} />}
      {/* The table is a reading aid; the exact payload is still one click away. */}
      <details className="trace-raw">
        <summary>Raw JSON</summary>
        <pre className="trace-json">{prettyJson({ args: call.args, result: call.result })}</pre>
      </details>
    </details>
  );
}

function TracePanel({ turns }: Props) {
  if (turns.length === 0) {
    return <p className="trace-empty">No agent activity yet. Send a message to see the tools it calls.</p>;
  }

  // Newest first — in a narrow sidebar the latest turn is what you came for.
  const newestFirst = [...turns].reverse();

  return (
    <div className="trace">
      {newestFirst.map((turn, index) => (
        // Only the newest turn starts open; when a new turn arrives the
        // previous one collapses on its own. startedAt is the key so the
        // history cap dropping the oldest turn doesn't remount the rest.
        <details key={turn.startedAt} className="trace-turn" open={index === 0}>
          <summary>
            <span className={`trace-status ${turn.status}`}>{STATUS_GLYPH[turn.status]}</span>
            <span className="trace-question">{turn.question}</span>
            <small>
              {turn.calls.length} {turn.calls.length === 1 ? "tool call" : "tool calls"} ·{" "}
              {turn.status === "running" ? "running…" : formatDuration(turn.durationMs)}
            </small>
          </summary>

          {turn.calls.length === 0 ? (
            <p className="trace-empty">
              {turn.status === "running" ? "Thinking…" : "The agent answered without calling any tools."}
            </p>
          ) : (
            turn.calls.map((call, i) => <CallView key={call.id ?? `${call.name}-${i}`} call={call} />)
          )}
        </details>
      ))}
    </div>
  );
}

export default TracePanel;
