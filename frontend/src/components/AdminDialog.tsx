// Reuses SettingsDialog's modal chrome and field/list styles (backdrop,
// dialog, settings-field, settings-hint, settings-access-list, ...) rather
// than duplicating them — this is a second, owner-only dialog of the same
// shape, not a different design.
import { useEffect, useState } from "react";

import { getAdminUsage, type AdminUsage } from "../api";
import "./AdminDialog.css";
import "./SettingsDialog.css";
import AccessSection from "./settings/AccessSection";

interface Props {
  idToken: string;
  onClose: () => void;
}

function UsageSection({ idToken }: { idToken: string }) {
  const [usage, setUsage] = useState<AdminUsage | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getAdminUsage(idToken)
      .then(setUsage)
      .catch(() => setError("Couldn't load usage."));
  }, [idToken]);

  return (
    <div className="settings-field">
      <div className="settings-label">Usage today</div>
      {error && <small className="settings-hint invalid">{error}</small>}
      {!usage && !error && <small className="settings-hint">Loading…</small>}
      {usage && (
        <>
          <table className="admin-usage-table">
            <tbody>
              {usage.users.map(({ email, count }) => (
                <tr key={email}>
                  <td>{email}</td>
                  <td className="admin-usage-count">{count}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <small className="settings-hint">
            Everyone combined: {usage.global.count} / {usage.global.limit} — a shared daily ceiling on top of each
            user's own, so it resets at midnight UTC.
          </small>
        </>
      )}
    </div>
  );
}

function AdminDialog({ idToken, onClose }: Props) {
  return (
    <div className="settings-backdrop" onMouseDown={onClose}>
      <div className="settings-dialog" role="dialog" aria-label="Admin" onMouseDown={(e) => e.stopPropagation()}>
        <h2>Admin</h2>

        <UsageSection idToken={idToken} />
        <AccessSection idToken={idToken} />

        <div className="settings-actions">
          <div />
          <div className="settings-actions-right">
            <button onClick={onClose}>Close</button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default AdminDialog;
