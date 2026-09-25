import { useEffect, useState } from "react";

import { getCategories, getTenantFacts, type Fact } from "../api";
import "./Facts.css";

interface Props {
  idToken: string;
  tenantId: string;
  // Bumped by the parent to refetch — facts are written asynchronously
  // (Pub/Sub), so a new one can land after the chat reply that caused it.
  refreshKey: number;
}

// The user's own categories come first, in their order; a category they
// removed later still shows its facts, after those.
function groupByCategory(facts: Fact[], order: string[]): [string, Fact[]][] {
  const groups = new Map<string, Fact[]>();
  for (const fact of facts) {
    const list = groups.get(fact.category) ?? [];
    list.push(fact);
    groups.set(fact.category, list);
  }

  const known = order.filter((c) => groups.has(c));
  const unknown = [...groups.keys()].filter((c) => !order.includes(c));
  return [...known, ...unknown].map((category) => [category, groups.get(category)!]);
}

function Facts({ idToken, tenantId, refreshKey }: Props) {
  const [facts, setFacts] = useState<Fact[]>([]);
  const [order, setOrder] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setError(null);
    getTenantFacts(idToken, tenantId)
      .then(setFacts)
      .catch((err) => setError(String(err)));
    // Only the order depends on this; without it the groups just follow the facts.
    getCategories(idToken)
      .then((c) => setOrder(c.categories))
      .catch(() => setOrder([]));
  }, [idToken, tenantId, refreshKey]);

  if (error) return <p>Error loading facts: {error}</p>;
  if (facts.length === 0) return <p>No facts recorded yet.</p>;

  return (
    <div className="facts">
      {groupByCategory(facts, order).map(([category, categoryFacts]) => (
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
