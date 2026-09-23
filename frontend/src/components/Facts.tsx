import { useEffect, useState } from "react";

import { getTenantFacts, type Fact } from "../api";
import "./Facts.css";

const CATEGORY_ORDER = ["architecture", "decision", "bug", "status", "todo"];

interface Props {
  idToken: string;
  tenantId: string;
  // Bumped by the parent to refetch — facts are written asynchronously
  // (Pub/Sub), so a new one can land after the chat reply that caused it.
  refreshKey: number;
}

function groupByCategory(facts: Fact[]): [string, Fact[]][] {
  const groups = new Map<string, Fact[]>();
  for (const fact of facts) {
    const list = groups.get(fact.category) ?? [];
    list.push(fact);
    groups.set(fact.category, list);
  }

  const known = CATEGORY_ORDER.filter((c) => groups.has(c));
  const unknown = [...groups.keys()].filter((c) => !CATEGORY_ORDER.includes(c));
  return [...known, ...unknown].map((category) => [category, groups.get(category)!]);
}

function Facts({ idToken, tenantId, refreshKey }: Props) {
  const [facts, setFacts] = useState<Fact[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setError(null);
    getTenantFacts(idToken, tenantId)
      .then(setFacts)
      .catch((err) => setError(String(err)));
  }, [idToken, tenantId, refreshKey]);

  if (error) return <p>Error loading facts: {error}</p>;
  if (facts.length === 0) return <p>No facts recorded yet.</p>;

  return (
    <div className="facts">
      {groupByCategory(facts).map(([category, categoryFacts]) => (
        <details key={category} className="facts-category" open>
          <summary>
            {category} ({categoryFacts.length})
          </summary>
          {categoryFacts.map((fact) => (
            <div key={fact.fact_id} className="fact-card">
              <p>{fact.content}</p>
              <small>{new Date(fact.created_at).toLocaleString()}</small>
            </div>
          ))}
        </details>
      ))}
    </div>
  );
}

export default Facts;
