import type { Tenant } from "../api";

interface Props {
  tenants: Tenant[];
  selectedId: string | null;
  onSelect: (tenantId: string) => void;
  // A failed load must not look like an empty account — "No projects
  // found" would tell the user their data is gone when it just didn't load.
  error?: boolean;
  onRetry?: () => void;
}

function TenantSelector({ tenants, selectedId, onSelect, error, onRetry }: Props) {
  if (error) {
    return (
      <div className="tenant-error">
        <span>Couldn't load your projects.</span>
        <button onClick={onRetry}>Retry</button>
      </div>
    );
  }

  if (tenants.length === 0) {
    return <p>No projects found.</p>;
  }

  return (
    <select value={selectedId ?? ""} onChange={(e) => onSelect(e.target.value)}>
      {tenants.map((tenant) => (
        <option key={tenant.tenant_id} value={tenant.tenant_id}>
          {tenant.name}
        </option>
      ))}
    </select>
  );
}

export default TenantSelector;
