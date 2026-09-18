import { useEffect, useRef, useState } from "react";

import "./AccountMenu.css";

interface Props {
  idToken: string;
  onSignOut: () => void;
  onChangeAccount: () => void;
}

interface TokenClaims {
  email: string;
  picture?: string;
}

function decodeClaims(idToken: string): TokenClaims {
  return JSON.parse(atob(idToken.split(".")[1]));
}

function AccountMenu({ idToken, onSignOut, onChangeAccount }: Props) {
  const [open, setOpen] = useState(false);
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
        {claims.picture ? (
          <img src={claims.picture} alt={claims.email} />
        ) : (
          <span>{claims.email[0]?.toUpperCase()}</span>
        )}
      </button>

      {open && (
        <div className="account-dropdown">
          <p className="account-email">{claims.email}</p>
          <button disabled title="Coming soon">
            Settings
          </button>
          <button onClick={onChangeAccount}>Change account</button>
          <button onClick={onSignOut}>Sign out</button>
        </div>
      )}
    </div>
  );
}

export default AccountMenu;
