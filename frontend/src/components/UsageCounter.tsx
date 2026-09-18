import { useEffect, useState } from "react";

import { getUsage, type Usage } from "../api";
import "./UsageCounter.css";

interface Props {
  idToken: string;
  // Bumped by the parent after each sent message so this refetches —
  // simpler than plumbing a shared count through props/context.
  refreshKey: number;
}

function UsageCounter({ idToken, refreshKey }: Props) {
  const [usage, setUsage] = useState<Usage | null>(null);

  useEffect(() => {
    getUsage(idToken).then(setUsage).catch(() => setUsage(null));
  }, [idToken, refreshKey]);

  if (!usage) return null;

  return (
    <div>
      <small>{usage.count} messages today</small>
      {usage.count >= usage.threshold && (
        <p className="usage-warning">You've sent a lot of messages today — just flagging it, nothing is blocked.</p>
      )}
    </div>
  );
}

export default UsageCounter;
