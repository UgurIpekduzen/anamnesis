import { useState } from "react";

import { NameTakenError, createTenant, deleteTenant, renameTenant, type Tenant } from "../api";
import ConfirmDialog from "./ConfirmDialog";
import "./TenantSelector.css";

interface Props {
  idToken: string;
  tenants: Tenant[];
  selectedId: string | null;
  onSelect: (tenantId: string) => void;
  // A failed load must not look like an empty account — "No projects
  // found" would tell the user their data is gone when it just didn't load.
  error?: boolean;
  onRetry?: () => void;
  // Project lifecycle is UI-only now, not a chat tool (see
  // agent/agent.py's build_agent docstring) — this refetches the list
  // and, for a new project, selects it.
  onChanged: (newlySelectedId?: string) => void;
}

// The sidebar's project dropdown, plus inline create/rename/delete —
// project lifecycle lives here, not in chat (see the onChanged prop above).
function TenantSelector({
  idToken,
  tenants,
  selectedId,
  onSelect,
  error,
  onRetry,
  onChanged,
}: Props) {
  const [adding, setAdding] = useState(false);
  const [newName, setNewName] = useState("");
  const [renaming, setRenaming] = useState(false);
  const [renameValue, setRenameValue] = useState("");
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const selected = tenants.find((t) => t.tenant_id === selectedId) ?? null;

  async function submitAdd() {
    const name = newName.trim();
    if (!name) return;
    setBusy(true);
    setActionError(null);
    try {
      const { tenant_id } = await createTenant(idToken, name);
      setAdding(false);
      setNewName("");
      onChanged(tenant_id);
    } catch (e) {
      setActionError(
        e instanceof NameTakenError ? e.message : "Couldn't create the project. Please try again.",
      );
    }
    setBusy(false);
  }

  async function submitRename() {
    if (!selected) return;
    const name = renameValue.trim();
    if (!name) return;
    setBusy(true);
    setActionError(null);
    try {
      await renameTenant(idToken, selected.tenant_id, name);
      setRenaming(false);
      onChanged();
    } catch {
      setActionError("Couldn't rename the project. Please try again.");
    }
    setBusy(false);
  }

  async function confirmDelete() {
    if (!selected) return;
    setConfirmingDelete(false);
    setBusy(true);
    setActionError(null);
    try {
      await deleteTenant(idToken, selected.tenant_id);
      onChanged();
    } catch {
      setActionError("Couldn't delete the project. Please try again.");
    }
    setBusy(false);
  }

  if (error) {
    return (
      <div className="tenant-error">
        <span>Couldn't load your projects.</span>
        <button onClick={onRetry}>Retry</button>
      </div>
    );
  }

  return (
    <div className="tenant-selector">
      {/* New project sits above the selector; its form opens in the same place. */}
      {adding ? (
        <div className="tenant-row">
          <input
            autoFocus
            placeholder="Project name"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submitAdd()}
            disabled={busy}
          />
          <button onClick={submitAdd} disabled={busy || !newName.trim()}>
            Add
          </button>
          <button
            onClick={() => {
              setAdding(false);
              setNewName("");
              setActionError(null);
            }}
            disabled={busy}
          >
            Cancel
          </button>
        </div>
      ) : (
        !renaming && (
          <button className="tenant-add" onClick={() => setAdding(true)} disabled={busy}>
            + New project
          </button>
        )
      )}

      {tenants.length === 0 && !adding ? (
        <p>No projects found.</p>
      ) : (
        <div className="tenant-row">
          <select
            value={selectedId ?? ""}
            onChange={(e) => onSelect(e.target.value)}
            disabled={adding || renaming}
          >
            {tenants.map((tenant) => (
              <option key={tenant.tenant_id} value={tenant.tenant_id}>
                {tenant.name}
              </option>
            ))}
          </select>
          {selected && !adding && !renaming && (
            <>
              <button
                className="icon-button"
                title="Rename project"
                onClick={() => {
                  setRenameValue(selected.name);
                  setRenaming(true);
                }}
                disabled={busy}
              >
                ✎
              </button>
              <button
                className="icon-button"
                title="Delete project"
                onClick={() => setConfirmingDelete(true)}
                disabled={busy}
              >
                🗑
              </button>
            </>
          )}
        </div>
      )}

      {renaming && (
        <div className="tenant-row">
          <input
            autoFocus
            value={renameValue}
            onChange={(e) => setRenameValue(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submitRename()}
            disabled={busy}
          />
          <button onClick={submitRename} disabled={busy || !renameValue.trim()}>
            Save
          </button>
          <button onClick={() => setRenaming(false)} disabled={busy}>
            Cancel
          </button>
        </div>
      )}

      {actionError && <p className="tenant-action-error">{actionError}</p>}

      {confirmingDelete && selected && (
        <ConfirmDialog
          title={`Delete "${selected.name}"?`}
          message="This deletes the whole project, including its facts and saved chat history. This can't be undone."
          confirmLabel="Delete"
          cancelLabel="Keep"
          onCancel={() => setConfirmingDelete(false)}
          onConfirm={confirmDelete}
        />
      )}
    </div>
  );
}

export default TenantSelector;
