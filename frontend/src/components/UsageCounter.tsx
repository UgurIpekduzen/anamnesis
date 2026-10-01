import { useEffect, useState } from "react";

import { getUsage, type Usage } from "../api";
import "./UsageCounter.css";

interface Props {
  idToken: string;
  // Bumped by the parent after each sent message so this refetches —
  // simpler than plumbing a shared count through props/context.
  refreshKey: number;
}

// "Resets in 5h 12m" — minutes only in the last hour, so it never reads
// "0h 12m".
function formatResetsIn(resetsAt: string, now: number): string {
  const minutes = Math.max(0, Math.ceil((new Date(resetsAt).getTime() - now) / 60000));
  if (minutes < 60) return `${minutes}m`;
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

function UsageCounter({ idToken, refreshKey }: Props) {
  const [usage, setUsage] = useState<Usage | null>(null);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    getUsage(idToken)
      .then(setUsage)
      .catch(() => setUsage(null));
  }, [idToken, refreshKey]);

  // Keeps the countdown moving while the page sits open.
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 60000);
    return () => clearInterval(timer);
  }, []);

  if (!usage) return null;

  const percent = Math.min(100, Math.round((usage.count / usage.limit) * 100));
  // The user's own warning threshold, shown as a tick on the bar; capped so
  // one set above the hard limit can't push it off the end.
  const thresholdPercent = Math.min(100, (usage.threshold / usage.limit) * 100);
  const state =
    usage.count >= usage.limit ? "full" : usage.count >= usage.threshold ? "warning" : "ok";

  return (
    <div className="usage">
      <h3 className="usage-title">Usage</h3>
      <div className="usage-row">
        <span>Today</span>
        <span>{percent}%</span>
      </div>
      <div
        className={`usage-bar usage-bar-${state}`}
        role="progressbar"
        aria-valuenow={usage.count}
        aria-valuemin={0}
        aria-valuemax={usage.limit}
        aria-label="Messages sent today"
        title={`${usage.count} of ${usage.limit} messages`}
      >
        <div className="usage-bar-fill" style={{ width: `${percent}%` }} />
        <div
          className="usage-bar-threshold"
          style={{ left: `${thresholdPercent}%` }}
          title="Your warning threshold"
        />
      </div>
      <small className="usage-meta">Resets in {formatResetsIn(usage.resets_at, now)}</small>
      {state === "full" && (
        <p className="usage-warning">
          Daily limit reached — new messages are refused until it resets.
        </p>
      )}
      {state === "warning" && (
        <p className="usage-warning">
          You've sent a lot of messages today — just flagging it, nothing is blocked yet.
        </p>
      )}
    </div>
  );
}

export default UsageCounter;
