import { useEffect, useState } from "react";

import {
  addAllowedEmail,
  getAllowedEmails,
  markUnlimited,
  removeAllowedEmail,
  unmarkUnlimited,
  type AllowedEmails,
} from "../../api";

interface Props {
  idToken: string;
}

function AccessSection({ idToken }: Props) {
  // null: not an owner (or still loading) — the whole section stays
  // hidden, since a non-owner can't use it anyway (APPCE-94).
  const [allowedEmails, setAllowedEmails] = useState<AllowedEmails | null>(null);
  const [newEmail, setNewEmail] = useState("");
  const [accessError, setAccessError] = useState<string | null>(null);
  const [accessBusy, setAccessBusy] = useState(false);

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
      const { extra_emails } = await addAllowedEmail(idToken, newEmail.trim());
      setAllowedEmails((prev) => (prev ? { ...prev, extra_emails } : prev));
      setNewEmail("");
    } catch (e) {
      setAccessError(e instanceof Error ? e.message : "Couldn't add that email.");
    }
    setAccessBusy(false);
  }

  async function removeEmail(email: string) {
    setAccessBusy(true);
    setAccessError(null);
    try {
      const { extra_emails } = await removeAllowedEmail(idToken, email);
      // The backend also drops the email's unlimited flag when it's removed.
      setAllowedEmails((prev) =>
        prev ? { ...prev, extra_emails, unlimited_emails: prev.unlimited_emails.filter((e) => e !== email) } : prev,
      );
    } catch {
      setAccessError("Couldn't remove that email. Please try again.");
    }
    setAccessBusy(false);
  }

  async function toggleUnlimited(email: string, unlimited: boolean) {
    setAccessBusy(true);
    setAccessError(null);
    try {
      const { unlimited_emails } = unlimited ? await unmarkUnlimited(idToken, email) : await markUnlimited(idToken, email);
      setAllowedEmails((prev) => (prev ? { ...prev, unlimited_emails } : prev));
    } catch (e) {
      setAccessError(e instanceof Error ? e.message : "Couldn't change that.");
    }
    setAccessBusy(false);
  }

  if (!allowedEmails) return null;

  return (
    <div className="settings-field">
      <div className="settings-label">Access</div>
      <small className="settings-hint">
        Anyone below can sign in to their own, fully separate projects — never yours. By default they're subject to a
        one-time lifetime message cap; mark someone "Unlimited" to exempt them from it (e.g. a collaborator, not a
        one-off tester).
      </small>
      <ul className="settings-access-list">
        {allowedEmails.owner_emails.map((email) => (
          <li key={email}>
            {email} <span className="settings-hint">(owner)</span>
          </li>
        ))}
        {allowedEmails.extra_emails.map((email) => {
          const unlimited = allowedEmails.unlimited_emails.includes(email);
          return (
            <li key={email}>
              <span>{email}</span>
              <button
                className="settings-access-unlimited"
                onClick={() => toggleUnlimited(email, unlimited)}
                disabled={accessBusy}
                aria-pressed={unlimited}
              >
                {unlimited ? "Unlimited" : "Mark unlimited"}
              </button>
              <button
                className="settings-access-remove"
                onClick={() => removeEmail(email)}
                disabled={accessBusy}
                aria-label={`Remove ${email}`}
              >
                ×
              </button>
            </li>
          );
        })}
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
    </div>
  );
}

export default AccessSection;
