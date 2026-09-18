import { useEffect, useState } from "react";

import { getTenantFacts, type Fact } from "../api";

const CATEGORY_ORDER = ["architecture", "decision", "bug", "status", "todo"];

interface Props {
  idToken: string;
  tenantId: string;
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

function Facts({ idToken, tenantId }: Props) {
  const [facts, setFacts] = useState<Fact[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setError(null);
    getTenantFacts(idToken, tenantId)
      .then(setFacts)
      .catch((err) => setError(String(err)));
  }, [idToken, tenantId]);

  if (error) return <p>Error loading facts: {error}</p>;
  if (facts.length === 0) return <p>No facts recorded yet.</p>;

  return (
    <div>
      {groupByCategory(facts).map(([category, categoryFacts]) => (
        <details key={category} open>
          <summary>
            {category} ({categoryFacts.length})
          </summary>
          {categoryFacts.map((fact) => (
            <div key={fact.fact_id} style={{ border: "1px solid #444", borderRadius: 8, padding: 8, margin: "8px 0" }}>
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
