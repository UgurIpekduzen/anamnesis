import type { Tenant } from "../api";

interface Props {
  tenants: Tenant[];
  selectedId: string | null;
  onSelect: (tenantId: string) => void;
}

function TenantSelector({ tenants, selectedId, onSelect }: Props) {
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
