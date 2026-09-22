import { useEffect, useMemo, useReducer, useRef, useState } from "react";

import "./App.css";
import { listTenants, type Tenant } from "./api";
import AccountMenu from "./components/AccountMenu";
import Auth from "./components/Auth";
import Chat from "./components/Chat";
import Facts from "./components/Facts";
import SettingsDialog from "./components/SettingsDialog";
import TenantSelector from "./components/TenantSelector";
import TracePanel from "./components/TracePanel";
import UsageCounter from "./components/UsageCounter";
import { initGoogleAuth, whenGoogleReady } from "./googleAuth";
import { tokenSubject } from "./tokenIdentity";
import { traceReducer, type ChatEvent } from "./trace";

type SidebarTab = "facts" | "trace";

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
  const [factsRefreshKey, setFactsRefreshKey] = useState(0);
  const [sidebarTab, setSidebarTab] = useState<SidebarTab>("facts");
  const [traceTurns, dispatchTrace] = useReducer(traceReducer, []);
  const [tenantsError, setTenantsError] = useState(false);
  const [tenantsReloadKey, setTenantsReloadKey] = useState(0);
  const [usageRefreshKey, setUsageRefreshKey] = useState(0);
  const [sidebarWidth, setSidebarWidth] = useState(280);
  const isResizing = useRef(false);
  const [googleReady, setGoogleReady] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);

  // The token is refreshed silently about every 50 minutes; the account it
  // belongs to is what decides whether the project list is stale.
  const userId = useMemo(() => tokenSubject(idToken), [idToken]);
  const idTokenRef = useRef(idToken);
  idTokenRef.current = idToken;

  useEffect(() => {
    if (!userId || !idTokenRef.current) return;
    // Clear immediately (not just on the fetch resolving) so Chat/Facts
    // — gated on selectedTenantId — briefly unmount instead of running
    // a moment longer against the previous account's stale tenant_id
    // while the new account's list is still loading (matters most for
    // "Change account", which swaps idToken without a full page reset).
    // Keyed on the account, not the token: a plain token refresh must not
    // reset the selected project or throw away the Trace (APPCE-65).
    setTenants([]);
    setSelectedTenantId(null);
    setTenantsError(false);

    // Ignore a response that lands after the token changed (or after a
    // retry) — it belongs to a request nobody is waiting on anymore.
    let cancelled = false;
    listTenants(idTokenRef.current)
      .then((fetched) => {
        if (cancelled) return;
        setTenants(fetched);
        setSelectedTenantId(fetched[0]?.tenant_id ?? null);
      })
      .catch(() => {
        if (!cancelled) setTenantsError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [userId, tenantsReloadKey]);

  useEffect(() => {
    return whenGoogleReady(() => {
      initGoogleAuth(setIdToken);
      // Auth.tsx waits for this before calling renderButton — GIS
      // requires initialize() to have already run, and its own polling
      // for window.google readiness raced this effect's, sometimes
      // rendering the button before initialize() had been called at all.
      setGoogleReady(true);
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

  // Everything Chat reports funnels through here: the usage counter and
  // the facts list refresh off it, and the Trace tab is built from it.
  function handleChatEvent(event: ChatEvent) {
    dispatchTrace({ ...event, at: Date.now() });
    // On send, and again when the turn ends: the server counts the message
    // alongside the model call, so the count read right after sending can
    // still be the old one (APPCE-72).
    if (event.type === "sent" || event.type === "answered" || event.type === "failed") {
      setUsageRefreshKey((k) => k + 1);
    }
    // A fact the agent just recorded lands asynchronously (Pub/Sub), so
    // this refetch can beat it — the Facts refresh button covers that.
    if (event.type === "answered") setFactsRefreshKey((k) => k + 1);
  }

  // The Trace belongs to one project's conversation, like the chat itself.
  useEffect(() => {
    dispatchTrace({ type: "cleared", at: Date.now() });
  }, [selectedTenantId]);

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
          <Auth ready={googleReady} />
        </div>
      </div>
    );
  }

  return (
    <div className="app">
      <AccountMenu
        idToken={idToken}
        onOpenSettings={() => setSettingsOpen(true)}
        onSignOut={signOut}
        onChangeAccount={changeAccount}
      />

      {settingsOpen && (
        <SettingsDialog
          idToken={idToken}
          onClose={() => setSettingsOpen(false)}
          // The warning threshold lives in Settings, so the counter in the
          // sidebar has to refetch to pick up a new one.
          onSaved={() => setUsageRefreshKey((k) => k + 1)}
        />
      )}

      <aside className="sidebar" style={{ width: sidebarWidth }}>
        <UsageCounter idToken={idToken} refreshKey={usageRefreshKey} />
        <TenantSelector
          tenants={tenants}
          selectedId={selectedTenantId}
          onSelect={setSelectedTenantId}
          error={tenantsError}
          onRetry={() => setTenantsReloadKey((k) => k + 1)}
        />

        <div className="tabs">
          <button
            className={`tab ${sidebarTab === "facts" ? "active" : ""}`}
            onClick={() => setSidebarTab("facts")}
          >
            Facts
          </button>
          <button
            className={`tab ${sidebarTab === "trace" ? "active" : ""}`}
            onClick={() => setSidebarTab("trace")}
          >
            Trace
            {traceTurns.length > 0 && <span className="tab-badge">{traceTurns.length}</span>}
          </button>
          {sidebarTab === "facts" && (
            <button
              className="icon-button"
              title="Refresh facts"
              onClick={() => setFactsRefreshKey((k) => k + 1)}
              disabled={!selectedTenantId}
            >
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="23 4 23 10 17 10" />
                <polyline points="1 20 1 14 7 14" />
                <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
              </svg>
            </button>
          )}
        </div>

        <div className="sidebar-panel">
          {sidebarTab === "trace" ? (
            <TracePanel turns={traceTurns} />
          ) : selectedTenantId ? (
            // Keyed by tenant so switching projects doesn't flash the
            // previous project's facts while the new list loads.
            <Facts key={selectedTenantId} idToken={idToken} tenantId={selectedTenantId} refreshKey={factsRefreshKey} />
          ) : (
            <p className="sidebar-empty">Select a project to see its facts.</p>
          )}
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

          <Chat
            key={selectedTenantId ?? "none"}
            idToken={idToken}
            tenantId={selectedTenantId}
            onEvent={handleChatEvent}
          />
        </div>
      </main>
    </div>
  );
}

export default App;
