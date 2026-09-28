import { useEffect, useState } from "react";

import {
  addAllowedEmail,
  getAdminUsage,
  getAllowedEmails,
  removeAllowedEmail,
  setRole,
  wipeUser,
  type AllowedEmails,
  type AdminUsage,
  type Role,
} from "../../api";
import HintLabel from "./HintLabel";
import WipeUserDialog from "../WipeUserDialog";

interface Props {
  idToken: string;
}

interface Row {
  email: string;
  role: Role | "admin";
  count: number;
}

// One table instead of a separate "Usage today" list and "Access" list —
// both were keyed by the same set of emails, so showing them side by side
// per row (rather than looking a name up twice) is the more direct read.
function UsersSection({ idToken }: Props) {
  // null: not an owner (or still loading) — the whole section stays
  // hidden, since a non-owner can't use it anyway (APPCE-94).
  const [allowedEmails, setAllowedEmails] = useState<AllowedEmails | null>(null);
  const [usage, setUsage] = useState<AdminUsage | null>(null);
  const [newEmail, setNewEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // The email a "Delete data" click is about to wipe, or null when the
  // confirmation dialog is closed (APPCE-123).
  const [wipeTarget, setWipeTarget] = useState<string | null>(null);

  function refreshUsage() {
    getAdminUsage(idToken)
      .then(setUsage)
      .catch(() => setError("Couldn't load usage."));
  }

  useEffect(() => {
    // A 403 (not an owner) resolves to null, not a caught error — most
    // users simply never see this section, that's not a failure to report.
    getAllowedEmails(idToken)
      .then(setAllowedEmails)
      .catch(() => setError("Couldn't load account access."));
    refreshUsage();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idToken]);

  async function addEmail() {
    setBusy(true);
    setError(null);
    try {
      const { extra_users } = await addAllowedEmail(idToken, newEmail.trim());
      setAllowedEmails((prev) => (prev ? { ...prev, extra_users } : prev));
      setNewEmail("");
      refreshUsage();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't add that email.");
    }
    setBusy(false);
  }

  async function removeEmail(email: string) {
    setBusy(true);
    setError(null);
    try {
      const { extra_users } = await removeAllowedEmail(idToken, email);
      setAllowedEmails((prev) => (prev ? { ...prev, extra_users } : prev));
      refreshUsage();
    } catch {
      setError("Couldn't remove that email. Please try again.");
    }
    setBusy(false);
  }

  async function changeRole(email: string, role: Role) {
    setBusy(true);
    setError(null);
    try {
      const { extra_users } = await setRole(idToken, email, role);
      setAllowedEmails((prev) => (prev ? { ...prev, extra_users } : prev));
      refreshUsage();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't change that.");
    }
    setBusy(false);
  }

  async function confirmWipe() {
    if (!wipeTarget) return;
    const { extra_users } = await wipeUser(idToken, wipeTarget, wipeTarget);
    setAllowedEmails((prev) => (prev ? { ...prev, extra_users } : prev));
    setWipeTarget(null);
    refreshUsage();
  }

  if (!allowedEmails) return null;

  const counts = new Map(usage?.users.map(({ email, count }) => [email, count]));
  const rows: Row[] = [
    ...allowedEmails.owner_emails.map((email) => ({ email, role: "admin" as const, count: counts.get(email) ?? 0 })),
    ...allowedEmails.extra_users.map(({ email, role }) => ({ email, role, count: counts.get(email) ?? 0 })),
  ];

  return (
    <div className="settings-field">
      <HintLabel label="Users" variant="section">
        Anyone below can sign in to their own, fully separate projects — never yours.
        <ul>
          <li>
            <strong>Tester</strong> — the default: a one-time lifetime message cap
          </li>
          <li>
            <strong>User</strong> — exempt from that cap (e.g. a collaborator, not a one-off tester)
          </li>
        </ul>
      </HintLabel>
      <table className="admin-users-table">
        <colgroup>
          <col />
          <col className="admin-users-role-col" />
          <col className="admin-users-count-col" />
          <col className="admin-users-action-col" />
          <col className="admin-users-action-col" />
        </colgroup>
        <thead>
          <tr>
            <th>Email</th>
            <th>Role</th>
            <th>Today</th>
            <th />
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map(({ email, role, count }) => (
            <tr key={email}>
              <td className="admin-users-email">{email}</td>
              <td>
                {role === "admin" ? (
                  <span className="admin-users-role">Admin</span>
                ) : (
                  <button
                    className="settings-access-role"
                    onClick={() => changeRole(email, role === "user" ? "tester" : "user")}
                    disabled={busy}
                    aria-pressed={role === "user"}
                  >
                    {role === "user" ? "User" : "Tester"}
                  </button>
                )}
              </td>
              <td className="admin-users-count">{count}</td>
              <td className="admin-users-action">
                {role !== "admin" && (
                  <button
                    className="settings-access-remove"
                    onClick={() => removeEmail(email)}
                    disabled={busy}
                    aria-label={`Remove ${email}`}
                    title="Remove access"
                  >
                    ×
                  </button>
                )}
              </td>
              <td className="admin-users-action">
                {role !== "admin" && (
                  <button
                    className="settings-access-wipe"
                    onClick={() => setWipeTarget(email)}
                    disabled={busy}
                    aria-label={`Delete ${email}'s data`}
                    title="Remove access and permanently delete their data"
                  >
                    🗑
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {usage && (
        <small className="settings-hint">
          Everyone combined: {usage.global.count} / {usage.global.limit} — a shared daily ceiling on top of each
          user's own, so it resets at midnight UTC.
        </small>
      )}
      <div className="admin-users-add">
        <input
          placeholder="Email to grant access to"
          value={newEmail}
          onChange={(e) => setNewEmail(e.target.value)}
          aria-invalid={!!error}
        />
        <button onClick={addEmail} disabled={!newEmail.trim() || busy}>
          {busy ? "Adding…" : "Add"}
        </button>
      </div>
      {error && <small className="settings-hint invalid">{error}</small>}
      {wipeTarget && (
        <WipeUserDialog email={wipeTarget} onConfirm={confirmWipe} onCancel={() => setWipeTarget(null)} />
      )}
    </div>
  );
}

export default UsersSection;
