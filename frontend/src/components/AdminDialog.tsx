// Reuses SettingsDialog's modal chrome and field styles (backdrop, dialog,
// settings-field, settings-hint, ...) rather than duplicating them — this
// is a second, owner-only dialog of the same shape, not a different design.
import AlertsSection from "./settings/AlertsSection";
import BrokenConnectionsSection from "./settings/BrokenConnectionsSection";
import MessageSettingsSection from "./settings/MessageSettingsSection";
import UsersSection from "./settings/UsersSection";
import "./AdminDialog.css";
import "./SettingsDialog.css";

interface Props {
  idToken: string;
  onClose: () => void;
}

// This component trusts its caller to gate access: it renders unconditionally
// once mounted, so App.tsx only ever mounts it after AccountMenu has already
// checked isOwner.
function AdminDialog({ idToken, onClose }: Props) {
  return (
    <div className="settings-backdrop" onMouseDown={onClose}>
      <div
        className="settings-dialog"
        role="dialog"
        aria-label="Admin"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="settings-header">
          <h2>Admin</h2>
          <button className="settings-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>

        <UsersSection idToken={idToken} />
        <MessageSettingsSection idToken={idToken} />
        <BrokenConnectionsSection idToken={idToken} />
        <AlertsSection idToken={idToken} />
      </div>
    </div>
  );
}

export default AdminDialog;
