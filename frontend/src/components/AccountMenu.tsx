import { useEffect, useRef, useState } from "react";

import "./AccountMenu.css";

interface Props {
  idToken: string;
  onOpenSettings: () => void;
  onSignOut: () => void;
  onChangeAccount: () => void;
  // null while still being determined — the entry stays hidden either way,
  // so it never flashes in for someone who turns out not to be an owner.
  isOwner: boolean | null;
  onOpenAdmin: () => void;
}

interface TokenClaims {
  email: string;
  picture?: string;
}

function decodeClaims(idToken: string): TokenClaims {
  return JSON.parse(atob(idToken.split(".")[1]));
}

function AccountMenu({ idToken, onOpenSettings, onSignOut, onChangeAccount, isOwner, onOpenAdmin }: Props) {
  const [open, setOpen] = useState(false);
  const [imgFailed, setImgFailed] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const claims = decodeClaims(idToken);

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  return (
    <div className="account-menu" ref={menuRef}>
      <button className="account-avatar" onClick={() => setOpen((o) => !o)} title={claims.email}>
        {claims.picture && !imgFailed ? (
          // Google's photo URLs occasionally 404/CORS-fail — fall back to
          // the initial-letter avatar instead of showing a broken image icon.
          <img src={claims.picture} alt={claims.email} onError={() => setImgFailed(true)} />
        ) : (
          <span>{claims.email[0]?.toUpperCase()}</span>
        )}
      </button>

      {open && (
        <div className="account-dropdown">
          <p className="account-email">{claims.email}</p>
          <button
            onClick={() => {
              setOpen(false);
              onOpenSettings();
            }}
          >
            Settings
          </button>
          {isOwner && (
            <button
              onClick={() => {
                setOpen(false);
                onOpenAdmin();
              }}
            >
              Admin
            </button>
          )}
          <button onClick={onChangeAccount}>Change account</button>
          <button onClick={onSignOut}>Sign out</button>
        </div>
      )}
    </div>
  );
}

export default AccountMenu;
