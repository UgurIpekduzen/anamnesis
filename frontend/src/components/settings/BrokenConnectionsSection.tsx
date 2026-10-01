import { useEffect, useState } from "react";

import { getBrokenConnections, type BrokenConnection } from "../../api";
import HintLabel from "./HintLabel";

interface Props {
  idToken: string;
}

const KIND_LABEL: Record<BrokenConnection["kind"], string> = {
  auth: "Token invalid or expired",
  not_found: "Repository not found or inaccessible",
  other: "Unknown error",
};

function formatFailedAt(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

// A tenant drops off this list on its own once its next poll succeeds
// — nothing here needs to be dismissed or cleared by hand.
function BrokenConnectionsSection({ idToken }: Props) {
  const [connections, setConnections] = useState<BrokenConnection[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getBrokenConnections(idToken)
      .then(setConnections)
      .catch(() => setError("Couldn't load connection status."));
  }, [idToken]);

  // Distinct from AlertsSection/UsersSection's "stay hidden until loaded"
  // gate: those never fail this visibly, but a fetch failure here still
  // needs to reach the owner, so it can't hide behind the same
  // connections-only check (that left the error unreachable).
  if (!connections && !error) return null;

  return (
    <div className="settings-field">
      <HintLabel label="Connections" variant="section">
        Whether each project's GitHub connection is currently failing to poll — the raw error isn't
        kept, only a rough reason. A connection drops off this list on its own once it's fixed and
        polls successfully again.
      </HintLabel>
      {error && <small className="settings-hint invalid">{error}</small>}
      {connections &&
        (connections.length === 0 ? (
          <small className="settings-hint">All connections are healthy.</small>
        ) : (
          <ul className="admin-connections-list">
            {connections.map((c) => (
              <li key={`${c.owner_uid}/${c.tenant_id}`} className="admin-connections-item">
                <div className="admin-connections-name">{c.name ?? c.tenant_id}</div>
                <div className="admin-connections-detail">
                  {KIND_LABEL[c.kind]}
                  {c.failed_at && ` — failing since ${formatFailedAt(c.failed_at)}`}
                </div>
              </li>
            ))}
          </ul>
        ))}
    </div>
  );
}

export default BrokenConnectionsSection;
