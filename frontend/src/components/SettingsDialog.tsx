import { useEffect } from "react";

import CategoriesSection from "./settings/CategoriesSection";
import GithubSection from "./settings/GithubSection";
import JiraSection from "./settings/JiraSection";
import "./SettingsDialog.css";

interface Props {
  idToken: string;
  onClose: () => void;
}

// Conversation memory and the daily message warning used to live here too,
// until APPCE-124 moved them to the owner-only Admin window — each of the
// sections below already saves itself as it's changed, so nothing here
// needs a form/Save/Cancel of its own anymore.
function SettingsDialog({ idToken, onClose }: Props) {
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div className="settings-backdrop" onMouseDown={onClose}>
      <div
        className="settings-dialog"
        role="dialog"
        aria-label="Settings"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <h2>Settings</h2>

        <CategoriesSection idToken={idToken} />
        <GithubSection idToken={idToken} />
        <JiraSection idToken={idToken} />

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

export default SettingsDialog;
