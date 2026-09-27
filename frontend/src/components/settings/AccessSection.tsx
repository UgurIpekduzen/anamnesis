import { useEffect, useState } from "react";

import {
  addAllowedEmail,
  getAllowedEmails,
  removeAllowedEmail,
  setRole,
  wipeUser,
  type AllowedEmails,
  type Role,
} from "../../api";
import WipeUserDialog from "../WipeUserDialog";

interface Props {
  idToken: string;
  // Called after any successful add/remove/role/wipe — lets AdminDialog
  // re-fetch Usage today so it never shows a stale row for someone just
  // removed or wiped.
  onChange: () => void;
}

function AccessSection({ idToken, onChange }: Props) {
  // null: not an owner (or still loading) — the whole section stays
  // hidden, since a non-owner can't use it anyway (APPCE-94).
  const [allowedEmails, setAllowedEmails] = useState<AllowedEmails | null>(null);
  const [newEmail, setNewEmail] = useState("");
  const [accessError, setAccessError] = useState<string | null>(null);
  const [accessBusy, setAccessBusy] = useState(false);
  // The email a "Delete data" click is about to wipe, or null when the
  // confirmation dialog is closed (APPCE-123).
  const [wipeTarget, setWipeTarget] = useState<string | null>(null);

  useEffect(() => {
    // A 403 (not an owner) resolves to null, not a caught error — most
    // users simply never see this section, that's not a failure to report.
    getAllowedEmails(idToken)
      .then(setAllowedEmails)
      .catch(() => setAccessError("Couldn't load account access."));
  }, [idToken]);

  async function addEmail() {
    setAccessBusy(true);
    setAccessError(null);
    try {
      const { extra_users } = await addAllowedEmail(idToken, newEmail.trim());
      setAllowedEmails((prev) => (prev ? { ...prev, extra_users } : prev));
      setNewEmail("");
      onChange();
    } catch (e) {
      setAccessError(e instanceof Error ? e.message : "Couldn't add that email.");
    }
    setAccessBusy(false);
  }

  async function removeEmail(email: string) {
    setAccessBusy(true);
    setAccessError(null);
    try {
      const { extra_users } = await removeAllowedEmail(idToken, email);
      setAllowedEmails((prev) => (prev ? { ...prev, extra_users } : prev));
      onChange();
    } catch {
      setAccessError("Couldn't remove that email. Please try again.");
    }
    setAccessBusy(false);
  }

  async function changeRole(email: string, role: Role) {
    setAccessBusy(true);
    setAccessError(null);
    try {
      const { extra_users } = await setRole(idToken, email, role);
      setAllowedEmails((prev) => (prev ? { ...prev, extra_users } : prev));
      onChange();
    } catch (e) {
      setAccessError(e instanceof Error ? e.message : "Couldn't change that.");
    }
    setAccessBusy(false);
  }

  async function confirmWipe() {
    if (!wipeTarget) return;
    const { extra_users } = await wipeUser(idToken, wipeTarget, wipeTarget);
    setAllowedEmails((prev) => (prev ? { ...prev, extra_users } : prev));
    setWipeTarget(null);
    onChange();
  }

  if (!allowedEmails) return null;

  return (
    <div className="settings-field">
      <div className="settings-label">Access</div>
      <small className="settings-hint">
        Anyone below can sign in to their own, fully separate projects — never yours. "Tester" is the default: a
        one-time lifetime message cap. Switch someone to "User" to exempt them from it (e.g. a collaborator, not a
        one-off tester).
      </small>
      <ul className="settings-access-list">
        {allowedEmails.owner_emails.map((email) => (
          <li key={email}>
            {email} <span className="settings-hint">(owner)</span>
          </li>
        ))}
        {allowedEmails.extra_users.map(({ email, role }) => (
          <li key={email}>
            <span>{email}</span>
            <button
              className="settings-access-role"
              onClick={() => changeRole(email, role === "user" ? "tester" : "user")}
              disabled={accessBusy}
              aria-pressed={role === "user"}
            >
              {role === "user" ? "User" : "Tester"}
            </button>
            <button
              className="settings-access-remove"
              onClick={() => removeEmail(email)}
              disabled={accessBusy}
              aria-label={`Remove ${email}`}
              title="Remove access"
            >
              ×
            </button>
            <button
              className="settings-access-wipe"
              onClick={() => setWipeTarget(email)}
              disabled={accessBusy}
              aria-label={`Delete ${email}'s data`}
              title="Remove access and permanently delete their data"
            >
              🗑
            </button>
          </li>
        ))}
      </ul>
      <input
        placeholder="Email to grant access to"
        value={newEmail}
        onChange={(e) => setNewEmail(e.target.value)}
        aria-invalid={!!accessError}
      />
      {accessError && <small className="settings-hint invalid">{accessError}</small>}
      <button onClick={addEmail} disabled={!newEmail.trim() || accessBusy}>
        {accessBusy ? "Adding…" : "Add"}
      </button>
      {wipeTarget && (
        <WipeUserDialog email={wipeTarget} onConfirm={confirmWipe} onCancel={() => setWipeTarget(null)} />
      )}
    </div>
  );
}

export default AccessSection;
