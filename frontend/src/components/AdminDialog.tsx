// Reuses SettingsDialog's modal chrome and field/list styles (backdrop,
// dialog, settings-field, settings-hint, settings-access-list, ...) rather
// than duplicating them — this is a second, owner-only dialog of the same
// shape, not a different design.
import "./SettingsDialog.css";
import AccessSection from "./settings/AccessSection";

interface Props {
  idToken: string;
  onClose: () => void;
}

function AdminDialog({ idToken, onClose }: Props) {
  return (
    <div className="settings-backdrop" onMouseDown={onClose}>
      <div className="settings-dialog" role="dialog" aria-label="Admin" onMouseDown={(e) => e.stopPropagation()}>
        <h2>Admin</h2>

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
