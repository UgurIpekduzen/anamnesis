import { useEffect, useState } from "react";

import {
  approvePendingFact,
  getPendingFactStats,
  getPendingFacts,
  rejectPendingFact,
  type PendingFact,
  type PendingFactStats,
} from "../api";
import "./Facts.css";
import "./PendingFacts.css";

interface Props {
  idToken: string;
  tenantId: string;
  // Bumped by the parent to refetch — a poll can add new
  // pending facts outside of any action taken in this UI.
  refreshKey: number;
  // Reported up so the sidebar tab can show a count badge, and so
  // approving a fact can trigger the real Facts list to refetch it.
  onCountChange: (count: number) => void;
  onApproved: () => void;
}

function PendingFacts({ idToken, tenantId, refreshKey, onCountChange, onApproved }: Props) {
  const [facts, setFacts] = useState<PendingFact[]>([]);
  const [error, setError] = useState<string | null>(null);
  // Tracks which card has a request in flight, so its own buttons disable
  // without freezing the rest of the list.
  const [busyId, setBusyId] = useState<string | null>(null);
  // How the facts staged so far were decided: shows how much to trust what
  // the model extracts. A nicety — the list works without it.
  const [stats, setStats] = useState<PendingFactStats | null>(null);

  function loadStats() {
    getPendingFactStats(idToken, tenantId)
      .then(setStats)
      .catch(() => setStats(null));
  }

  function load() {
    setError(null);
    getPendingFacts(idToken, tenantId)
      .then((fetched) => {
        setFacts(fetched);
        onCountChange(fetched.length);
      })
      .catch((err) => setError(String(err)));
  }

  useEffect(load, [idToken, tenantId, refreshKey, onCountChange]);
  useEffect(loadStats, [idToken, tenantId, refreshKey]);

  async function approve(pendingFactId: string) {
    setBusyId(pendingFactId);
    try {
      await approvePendingFact(idToken, tenantId, pendingFactId);
      const remaining = facts.filter((f) => f.pending_fact_id !== pendingFactId);
      setFacts(remaining);
      onCountChange(remaining.length);
      onApproved();
      loadStats();
    } catch (err) {
      setError(String(err));
    }
    setBusyId(null);
  }

  async function reject(pendingFactId: string) {
    setBusyId(pendingFactId);
    try {
      await rejectPendingFact(idToken, tenantId, pendingFactId);
      const remaining = facts.filter((f) => f.pending_fact_id !== pendingFactId);
      setFacts(remaining);
      onCountChange(remaining.length);
      loadStats();
    } catch (err) {
      setError(String(err));
    }
    setBusyId(null);
  }

  const decided = stats ? stats.approved + stats.rejected : 0;
  const rate =
    stats && decided > 0 ? (
      <div
        className="approval-rate"
        title="Facts extracted from GitHub that you approved, out of those you decided on"
      >
        <div className="approval-rate-row">
          <span>Approval rate</span>
          <span>{Math.round((stats.approved / decided) * 100)}%</span>
        </div>
        <div
          className="approval-bar"
          role="img"
          aria-label={`${stats.approved} approved, ${stats.rejected} rejected`}
        >
          {/* Sized by count, so a segment with nothing in it takes no room. */}
          {stats.approved > 0 && (
            <div className="approval-bar-approved" style={{ flexGrow: stats.approved }} />
          )}
          {stats.rejected > 0 && (
            <div className="approval-bar-rejected" style={{ flexGrow: stats.rejected }} />
          )}
        </div>
        <div className="approval-legend">
          <span className="approval-dot approval-dot-approved" /> {stats.approved} approved
          <span className="approval-dot approval-dot-rejected" /> {stats.rejected} rejected
        </div>
      </div>
    ) : null;

  if (error) return <p>Error loading pending facts: {error}</p>;
  if (facts.length === 0) {
    return (
      <>
        <p>Nothing waiting for review.</p>
        {rate}
      </>
    );
  }

  return (
    <div className="facts">
      {rate}
      {facts.map((fact) => (
        <div key={fact.pending_fact_id} className="fact-card pending-fact-card">
          <p>{fact.content}</p>
          <div className="pending-fact-meta">
            <span className="pending-fact-category">{fact.category}</span>
            {fact.source_url && (
              <a href={fact.source_url} target="_blank" rel="noopener noreferrer">
                source
              </a>
            )}
          </div>
          <div className="pending-fact-actions">
            <button
              className="pending-fact-approve"
              onClick={() => approve(fact.pending_fact_id)}
              disabled={busyId === fact.pending_fact_id}
            >
              Approve
            </button>
            <button
              onClick={() => reject(fact.pending_fact_id)}
              disabled={busyId === fact.pending_fact_id}
            >
              Reject
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

export default PendingFacts;
