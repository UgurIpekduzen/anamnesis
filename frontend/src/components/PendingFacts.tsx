import { useEffect, useState } from "react";

import { approvePendingFact, getPendingFacts, rejectPendingFact, type PendingFact } from "../api";
import "./Facts.css";
import "./PendingFacts.css";

interface Props {
  idToken: string;
  tenantId: string;
  // Bumped by the parent to refetch — a poll (APPCE-80) can add new
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

  function load() {
    setError(null);
    getPendingFacts(idToken, tenantId)
      .then((fetched) => {
        setFacts(fetched);
        onCountChange(fetched.length);
      })
      .catch((err) => setError(String(err)));
  }

  useEffect(load, [idToken, tenantId, refreshKey]);

  async function approve(pendingFactId: string) {
    setBusyId(pendingFactId);
    try {
      await approvePendingFact(idToken, tenantId, pendingFactId);
      const remaining = facts.filter((f) => f.pending_fact_id !== pendingFactId);
      setFacts(remaining);
      onCountChange(remaining.length);
      onApproved();
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
    } catch (err) {
      setError(String(err));
    }
    setBusyId(null);
  }

  if (error) return <p>Error loading pending facts: {error}</p>;
  if (facts.length === 0) return <p>Nothing waiting for review.</p>;

  return (
    <div className="facts">
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
            <button onClick={() => reject(fact.pending_fact_id)} disabled={busyId === fact.pending_fact_id}>
              Reject
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

export default PendingFacts;
