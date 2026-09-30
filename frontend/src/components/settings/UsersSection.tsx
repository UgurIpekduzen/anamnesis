import { useEffect, useState } from "react";

import {
  addAllowedEmail,
  listUsers,
  removeAllowedEmail,
  setRole,
  setUserName,
  wipeUser,
  type AdminUsersPage,
  type Role,
} from "../../api";
import ConfirmDialog from "../ConfirmDialog";
import HintLabel from "./HintLabel";
import WipeUserDialog from "../WipeUserDialog";

interface Props {
  idToken: string;
}

function formatInvitedAt(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

// One table instead of a separate "Usage today" list and "Access" list —
// both were keyed by the same set of emails, so showing them side by side
// per row (rather than looking a name up twice) is the more direct read.
// Backed by GET /admin/users, which also carries the owner-set
// display name and supports a search query — the table scrolls within a
// fixed height instead of pushing the rest of the dialog down as the
// invited list grows.
function UsersSection({ idToken }: Props) {
  // null: not an owner (or still loading) — the whole section stays
  // hidden, since a non-owner can't use it anyway.
  const [page, setPage] = useState<AdminUsersPage | null>(null);
  const [query, setQuery] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Local, per-row edit buffer so typing a name doesn't fire a save on
  // every keystroke — committed on blur/Enter instead.
  const [nameDrafts, setNameDrafts] = useState<Record<string, string>>({});
  // The email a "Delete data" click is about to wipe, or null when the
  // confirmation dialog is closed.
  const [wipeTarget, setWipeTarget] = useState<string | null>(null);
  // The email a Tester → User click is about to exempt from the lifetime
  // cap, or null when that confirmation is closed.
  const [userGrantTarget, setUserGrantTarget] = useState<string | null>(null);
  // The email a User → Tester click is about to re-apply the cap to, or
  // null when that confirmation is closed. The lifetime count never resets
  // (it kept counting while they were exempt), so this can lock them out
  // immediately if they're already past it — worth a heads-up either way.
  const [testerRevertTarget, setTesterRevertTarget] = useState<string | null>(null);

  function refresh(q: string) {
    listUsers(idToken, { q })
      .then(setPage)
      .catch(() => setError("Couldn't load users."));
  }

  useEffect(() => {
    refresh("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idToken]);

  // Debounced: a search request per keystroke would just get raced by the
  // next one anyway, and 403 users never reach this (page stays null until
  // the first successful load, see the early return below).
  useEffect(() => {
    if (!page) return;
    const id = setTimeout(() => refresh(query), 300);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);

  async function addEmail() {
    setBusy(true);
    setError(null);
    try {
      await addAllowedEmail(idToken, newEmail.trim());
      setNewEmail("");
      refresh(query);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't add that email.");
    }
    setBusy(false);
  }

  async function removeEmail(email: string) {
    setBusy(true);
    setError(null);
    try {
      await removeAllowedEmail(idToken, email);
      refresh(query);
    } catch {
      setError("Couldn't remove that email. Please try again.");
    }
    setBusy(false);
  }

  async function changeRole(email: string, role: Role) {
    setBusy(true);
    setError(null);
    try {
      await setRole(idToken, email, role);
      refresh(query);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't change that.");
    }
    setBusy(false);
  }

  async function confirmWipe() {
    if (!wipeTarget) return;
    await wipeUser(idToken, wipeTarget, wipeTarget);
    setWipeTarget(null);
    refresh(query);
  }

  async function saveName(email: string, current: string | null) {
    const draft = nameDrafts[email];
    if (draft === undefined || draft === (current ?? "")) return;
    try {
      await setUserName(idToken, email, draft);
      refresh(query);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save that name.");
    }
    setNameDrafts((prev) => {
      const { [email]: _drop, ...rest } = prev;
      return rest;
    });
  }

  if (!page) return null;

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
      <input
        className="admin-users-search"
        placeholder="Search by name or email"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      <div className="admin-users-table-wrap">
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
            {page.users.map(({ email, role, name, count, invited_at }) => (
              <tr key={email}>
                <td className="admin-users-email">
                  <div>{email}</div>
                  <input
                    className="admin-users-name-input"
                    placeholder="Enter a name"
                    value={nameDrafts[email] ?? name ?? ""}
                    onChange={(e) =>
                      setNameDrafts((prev) => ({ ...prev, [email]: e.target.value }))
                    }
                    onBlur={() => saveName(email, name)}
                    onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
                  />
                  {invited_at && (
                    <div className="admin-users-invited">Joined {formatInvitedAt(invited_at)}</div>
                  )}
                </td>
                <td>
                  {role === "admin" ? (
                    <span className="admin-users-role">Admin</span>
                  ) : (
                    <button
                      className="settings-access-role"
                      onClick={() =>
                        role === "user" ? setTesterRevertTarget(email) : setUserGrantTarget(email)
                      }
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
            {page.users.length === 0 && (
              <tr>
                <td colSpan={5} className="admin-users-empty">
                  No matches.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <small className="settings-hint">
        Everyone combined: {page.global.count} / {page.global.limit} — a shared daily ceiling on top
        of each user's own, so it resets at midnight UTC.
      </small>
      {wipeTarget && (
        <WipeUserDialog
          email={wipeTarget}
          onConfirm={confirmWipe}
          onCancel={() => setWipeTarget(null)}
        />
      )}
      {userGrantTarget && (
        <ConfirmDialog
          title="Switch to User?"
          message={`${userGrantTarget} will be exempt from the tester lifetime message cap. Use this for a trusted collaborator, not a one-off tester.`}
          confirmLabel="Switch to User"
          cancelLabel="Cancel"
          onConfirm={() => {
            changeRole(userGrantTarget, "user");
            setUserGrantTarget(null);
          }}
          onCancel={() => setUserGrantTarget(null)}
        />
      )}
      {testerRevertTarget && (
        <ConfirmDialog
          title="Switch to Tester?"
          message={`The lifetime message cap applies to ${testerRevertTarget} again. It never reset while they were exempt, so if they're already past it, they'll be locked out immediately.`}
          confirmLabel="Switch to Tester"
          cancelLabel="Cancel"
          onConfirm={() => {
            changeRole(testerRevertTarget, "tester");
            setTesterRevertTarget(null);
          }}
          onCancel={() => setTesterRevertTarget(null)}
        />
      )}
    </div>
  );
}

export default UsersSection;
