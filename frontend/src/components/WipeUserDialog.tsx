import { useEffect, useRef, useState } from "react";

import "./ConfirmDialog.css";

interface Props {
  email: string;
  onConfirm: () => Promise<void>;
  onCancel: () => void;
}

// Deleting a user's data is permanent and spans several collections
// — a single click, the way ConfirmDialog works, isn't enough
// friction for that. Delete only enables once the owner retypes the exact
// email, the same confirm-by-retyping db_backup's --confirm-project uses.
function WipeUserDialog({ email, onConfirm, onCancel }: Props) {
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape" && !busy) onCancel();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onCancel, busy]);

  async function handleConfirm() {
    setBusy(true);
    setError(null);
    try {
      await onConfirm();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't delete this user's data.");
      setBusy(false);
    }
  }

  return (
    <div className="confirm-backdrop" onClick={() => !busy && onCancel()}>
      <div
        className="confirm-dialog"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="wipe-title"
        aria-describedby="wipe-message"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="wipe-title">Delete {email}&apos;s data</h2>
        <p id="wipe-message">
          This permanently deletes every project, fact, connection and usage record for this email, and removes
          them from Access. This can&apos;t be undone. Type the email below to confirm.
        </p>
        <input
          ref={inputRef}
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          placeholder={email}
          disabled={busy}
          aria-label="Confirm email"
        />
        {error && <p className="confirm-error">{error}</p>}
        <div className="confirm-actions">
          <button onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button className="confirm-danger" onClick={handleConfirm} disabled={busy || typed !== email}>
            {busy ? "Deleting…" : "Delete"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default WipeUserDialog;
