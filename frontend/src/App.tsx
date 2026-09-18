import { useEffect, useRef, useState } from "react";

import "./App.css";
import { listTenants, type Tenant } from "./api";
import AccountMenu from "./components/AccountMenu";
import Auth from "./components/Auth";
import Chat from "./components/Chat";
import Facts from "./components/Facts";
import TenantSelector from "./components/TenantSelector";
import UsageCounter from "./components/UsageCounter";
import { initGoogleAuth, whenGoogleReady } from "./googleAuth";

type Tab = "chat" | "facts";

const MIN_SIDEBAR_WIDTH = 200;
const MAX_SIDEBAR_WIDTH = 480;

// Re-prompts in the background well before a token's ~1 hour lifetime
// runs out, so the user is (usually) never asked to sign in again
// mid-session — see APPCE-54 for the tradeoffs behind this. Lives at
// the app level (not Auth.tsx) since it must keep running after the
// sign-in screen unmounts.
const SILENT_REFRESH_INTERVAL_MS = 50 * 60 * 1000;

function App() {
  const [idToken, setIdToken] = useState<string | null>(null);
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [selectedTenantId, setSelectedTenantId] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("chat");
  const [usageRefreshKey, setUsageRefreshKey] = useState(0);
  const [sidebarWidth, setSidebarWidth] = useState(280);
  const isResizing = useRef(false);

  useEffect(() => {
    if (!idToken) return;
    // Clear immediately (not just on the fetch resolving) so Chat/Facts
    // — gated on selectedTenantId — briefly unmount instead of running
    // a moment longer against the previous account's stale tenant_id
    // while the new account's list is still loading (matters most for
    // "Change account", which swaps idToken without a full page reset).
    setTenants([]);
    setSelectedTenantId(null);
    listTenants(idToken).then((fetched) => {
      setTenants(fetched);
      setSelectedTenantId(fetched[0]?.tenant_id ?? null);
    });
  }, [idToken]);

  useEffect(() => {
    return whenGoogleReady(() => {
      initGoogleAuth(setIdToken);
      const refreshInterval = setInterval(() => {
        window.google?.accounts.id.prompt();
      }, SILENT_REFRESH_INTERVAL_MS);
      return () => clearInterval(refreshInterval);
    });
  }, []);

  useEffect(() => {
    function onMouseMove(e: MouseEvent) {
      if (!isResizing.current) return;
      const clamped = Math.min(Math.max(e.clientX, MIN_SIDEBAR_WIDTH), MAX_SIDEBAR_WIDTH);
      setSidebarWidth(clamped);
    }
    function onMouseUp() {
      isResizing.current = false;
    }
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, []);

  // disableAutoSelect stops GIS from silently re-selecting this same
  // account next time — without it, "sign out" would just log the user
  // straight back in.
  function signOut() {
    window.google?.accounts.id.disableAutoSelect();
    setIdToken(null);
  }

  // Opens Google's account picker directly over the current screen —
  // no need to sign out first. If they cancel, initGoogleAuth's
  // callback never fires and idToken (and the current screen) just
  // stays as it was.
  function changeAccount() {
    window.google?.accounts.id.disableAutoSelect();
    window.google?.accounts.id.prompt();
  }

  if (!idToken) {
    return (
      <div className="signin-screen">
        <div className="signin-gate">
          <h1>Anamnesis</h1>
          <p>Personal Project Context Engine</p>
          <Auth />
        </div>
      </div>
    );
  }

  return (
    <div className="app">
      <AccountMenu idToken={idToken} onSignOut={signOut} onChangeAccount={changeAccount} />

      <aside className="sidebar" style={{ width: sidebarWidth }}>
        <UsageCounter idToken={idToken} refreshKey={usageRefreshKey} />
        <TenantSelector tenants={tenants} selectedId={selectedTenantId} onSelect={setSelectedTenantId} />

        <div className="tabs">
          <button className={tab === "chat" ? "active" : ""} onClick={() => setTab("chat")}>
            Chat
          </button>
          <button className={tab === "facts" ? "active" : ""} onClick={() => setTab("facts")}>
            Facts
          </button>
        </div>
      </aside>

      <div
        className="resize-handle"
        onMouseDown={() => {
          isResizing.current = true;
        }}
      />

      <main className="main">
        <div className="main-inner">
          <h1>Anamnesis</h1>
          <p>Personal Project Context Engine</p>

          {tab === "chat" && (
            <Chat
              key={selectedTenantId ?? "none"}
              idToken={idToken}
              tenantId={selectedTenantId}
              onMessageSent={() => setUsageRefreshKey((k) => k + 1)}
            />
          )}
          {tab === "facts" &&
            (selectedTenantId ? (
              <Facts idToken={idToken} tenantId={selectedTenantId} />
            ) : (
              <p>Select a project to see its facts.</p>
            ))}
        </div>
      </main>
    </div>
  );
}

export default App;
