import { useEffect, useMemo, useReducer, useRef, useState } from "react";

import "./App.css";
import { getGithubConnection, getJiraConnection, listTenants, type JiraConnection, type Tenant } from "./api";
import AccountMenu from "./components/AccountMenu";
import Auth from "./components/Auth";
import Chat from "./components/Chat";
import Facts from "./components/Facts";
import PendingFacts from "./components/PendingFacts";
import ProjectLinks from "./components/ProjectLinks";
import SettingsDialog from "./components/SettingsDialog";
import TenantSelector from "./components/TenantSelector";
import TracePanel from "./components/TracePanel";
import UsageCounter from "./components/UsageCounter";
import { describePromptMoment, initGoogleAuth, whenGoogleReady } from "./googleAuth";
import { tokenSubject } from "./tokenIdentity";
import { traceReducer, type ChatEvent } from "./trace";

type SidebarTab = "facts" | "pending" | "trace";

const MIN_SIDEBAR_WIDTH = 200;
// The sidebar can be dragged as wide as the window allows, but the chat
// keeps at least this much room — otherwise the drag handle could leave the
// screen and the sidebar couldn't be dragged back (APPCE-73). App.css caps
// it the same way if the window is made smaller afterwards.
const MIN_MAIN_WIDTH = 320;

// Re-prompts in the background well before a token's ~1 hour lifetime
// runs out, so the user is (usually) never asked to sign in again
// mid-session — see APPCE-54 for the tradeoffs behind this. Lives at
// the app level (not Auth.tsx) since it must keep running after the
// sign-in screen unmounts.
const SILENT_REFRESH_INTERVAL_MS = 50 * 60 * 1000;

// When to re-read the facts after a fact was published: the write goes
// through Pub/Sub, so it usually lands within a couple of seconds.
const FACTS_RETRY_DELAYS_MS = [1500, 4000, 8000];

function App() {
  const [idToken, setIdToken] = useState<string | null>(null);
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [selectedTenantId, setSelectedTenantId] = useState<string | null>(null);
  const [factsRefreshKey, setFactsRefreshKey] = useState(0);
  const [sidebarTab, setSidebarTab] = useState<SidebarTab>("facts");
  const [traceTurns, dispatchTrace] = useReducer(traceReducer, []);
  const [tenantsError, setTenantsError] = useState(false);
  const [tenantsReloadKey, setTenantsReloadKey] = useState(0);
  // Whether the user's GitHub/Jira accounts are connected (APPCE-105) —
  // null until known. Re-read whenever Settings closes, where they change.
  const [githubConnected, setGithubConnected] = useState<boolean | null>(null);
  const [jiraConnection, setJiraConnection] = useState<JiraConnection | null>(null);
  const [connectionsReloadKey, setConnectionsReloadKey] = useState(0);
  // Set by TenantSelector right before a reload it triggered itself (e.g.
  // just created a project) — picked up once the fresh list lands, since
  // the list fetch below is async and would otherwise overwrite a
  // synchronous selection with its own fetched[0] fallback.
  const pendingTenantSelectRef = useRef<string | null>(null);
  const [usageRefreshKey, setUsageRefreshKey] = useState(0);
  const [pendingFactsRefreshKey, setPendingFactsRefreshKey] = useState(0);
  const [pendingFactsCount, setPendingFactsCount] = useState(0);
  const [sidebarWidth, setSidebarWidth] = useState(280);
  const isResizing = useRef(false);
  const [googleReady, setGoogleReady] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  // Set when the chat socket is rejected outright (APPCE-69) — shown on
  // the sign-in screen so the user knows why they landed back there.
  const [sessionExpired, setSessionExpired] = useState(false);

  // The token is refreshed silently about every 50 minutes; the account it
  // belongs to is what decides whether the project list is stale.
  const userId = useMemo(() => tokenSubject(idToken), [idToken]);
  const selectedTenant = tenants.find((t) => t.tenant_id === selectedTenantId) ?? null;
  const idTokenRef = useRef(idToken);
  idTokenRef.current = idToken;

  // Counts project-list requests so a late answer to an older one is dropped
  // (a quiet refresh must never overwrite a newer list or another account's).
  const tenantsRequestRef = useRef(0);
  // Pending re-fetches of the facts list after a fact was published.
  const factsRetryTimersRef = useRef<ReturnType<typeof setTimeout>[]>([]);

  // Re-read the project list without touching the selection, unlike the
  // effect below (which resets everything). Used after the assistant links a
  // GitHub repo or Jira key, so the project card shows it (APPCE-105).
  function refreshTenantsQuietly() {
    const token = idTokenRef.current;
    if (!token) return;
    const request = ++tenantsRequestRef.current;
    listTenants(token)
      .then((fetched) => {
        if (request === tenantsRequestRef.current) setTenants(fetched);
      })
      .catch(() => {});
  }

  useEffect(() => {
    if (!userId || !idTokenRef.current) return;
    tenantsRequestRef.current++;
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
        const pending = pendingTenantSelectRef.current;
        pendingTenantSelectRef.current = null;
        const preferred = pending && fetched.some((t) => t.tenant_id === pending) ? pending : fetched[0]?.tenant_id;
        setSelectedTenantId(preferred ?? null);
      })
      .catch(() => {
        if (!cancelled) setTenantsError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [userId, tenantsReloadKey]);

  useEffect(() => {
    if (!userId || !idTokenRef.current) return;
    let cancelled = false;
    // Two independent lookups: one failing must not hide the other. A
    // failure leaves the status unknown (no warning), not "disconnected".
    getGithubConnection(idTokenRef.current)
      .then((c) => !cancelled && setGithubConnected(c.connected))
      .catch(() => !cancelled && setGithubConnected(null));
    getJiraConnection(idTokenRef.current)
      .then((c) => !cancelled && setJiraConnection(c))
      .catch(() => !cancelled && setJiraConnection(null));
    return () => {
      cancelled = true;
    };
  }, [userId, connectionsReloadKey]);

  useEffect(() => {
    return whenGoogleReady(() => {
      initGoogleAuth((token) => {
        setSessionExpired(false);
        setIdToken(token);
      });
      // Auth.tsx waits for this before calling renderButton — GIS
      // requires initialize() to have already run, and its own polling
      // for window.google readiness raced this effect's, sometimes
      // rendering the button before initialize() had been called at all.
      setGoogleReady(true);
      const refreshInterval = setInterval(() => {
        // The notification carries no user data, just why nothing was
        // shown — logged so a silently-failing refresh (see APPCE-69) is
        // diagnosable from the console instead of invisible.
        window.google?.accounts.id.prompt((notification) => {
          const outcome = describePromptMoment(notification);
          if (outcome !== "displayed") console.info(`Background token refresh: ${outcome}`);
        });
      }, SILENT_REFRESH_INTERVAL_MS);
      return () => clearInterval(refreshInterval);
    });
  }, []);

  useEffect(() => {
    function onMouseMove(e: MouseEvent) {
      if (!isResizing.current) return;
      const maxWidth = window.innerWidth - MIN_MAIN_WIDTH;
      const clamped = Math.max(MIN_SIDEBAR_WIDTH, Math.min(e.clientX, maxWidth));
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
    // A fact the agent just recorded lands asynchronously (Pub/Sub), so a
    // single refetch when the turn ends can beat it. Ask again a few times
    // shortly after; the Facts refresh button stays as the last resort.
    if (event.type === "tool_result" && event.name === "publish_fact") {
      factsRetryTimersRef.current.forEach(clearTimeout);
      factsRetryTimersRef.current = FACTS_RETRY_DELAYS_MS.map((delay) =>
        setTimeout(() => setFactsRefreshKey((k) => k + 1), delay),
      );
    }
    if (event.type === "answered") {
      setFactsRefreshKey((k) => k + 1);
      // The assistant may just have linked a repo or a Jira key.
      refreshTenantsQuietly();
    }
  }

  // The Trace belongs to one project's conversation, like the chat itself.
  useEffect(() => {
    dispatchTrace({ type: "cleared", at: Date.now() });
    // A retry for the previous project's facts has no business firing now.
    factsRetryTimersRef.current.forEach(clearTimeout);
    factsRetryTimersRef.current = [];
  }, [selectedTenantId]);

  useEffect(() => () => factsRetryTimersRef.current.forEach(clearTimeout), []);

  // disableAutoSelect stops GIS from silently re-selecting this same
  // account next time — without it, "sign out" would just log the user
  // straight back in.
  function signOut() {
    window.google?.accounts.id.disableAutoSelect();
    setIdToken(null);
  }

  // The chat socket's cue that its token no longer checks out. Unlike
  // signOut, this doesn't call disableAutoSelect: if the background
  // refresh (App-level effect above) can silently sign the user back in,
  // it should be allowed to.
  function handleAuthFailed() {
    setSessionExpired(true);
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
          {sessionExpired && <p className="session-expired">Your session ended. Please sign in again.</p>}
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
          onClose={() => {
            setSettingsOpen(false);
            // Connecting or disconnecting an account happens in Settings.
            setConnectionsReloadKey((k) => k + 1);
          }}
          // The warning threshold lives in Settings, so the counter in the
          // sidebar has to refetch to pick up a new one.
          onSaved={() => setUsageRefreshKey((k) => k + 1)}
        />
      )}

      <aside className="sidebar" style={{ width: sidebarWidth }}>
        <UsageCounter idToken={idToken} refreshKey={usageRefreshKey} />
        <TenantSelector
          idToken={idToken}
          tenants={tenants}
          selectedId={selectedTenantId}
          onSelect={setSelectedTenantId}
          error={tenantsError}
          onRetry={() => setTenantsReloadKey((k) => k + 1)}
          onChanged={(newlySelectedId) => {
            pendingTenantSelectRef.current = newlySelectedId ?? null;
            setTenantsReloadKey((k) => k + 1);
          }}
        />
        {selectedTenant && !tenantsError && (
          <ProjectLinks
            key={selectedTenant.tenant_id}
            idToken={idToken}
            tenant={selectedTenant}
            githubConnected={githubConnected}
            jira={jiraConnection}
            onChanged={refreshTenantsQuietly}
          />
        )}

        <div className="tabs">
          <button
            className={`tab ${sidebarTab === "facts" ? "active" : ""}`}
            onClick={() => setSidebarTab("facts")}
          >
            Facts
          </button>
          <button
            className={`tab ${sidebarTab === "pending" ? "active" : ""}`}
            onClick={() => setSidebarTab("pending")}
          >
            Pending
            {pendingFactsCount > 0 && <span className="tab-badge">{pendingFactsCount}</span>}
          </button>
          <button
            className={`tab ${sidebarTab === "trace" ? "active" : ""}`}
            onClick={() => setSidebarTab("trace")}
          >
            Trace
            {traceTurns.length > 0 && <span className="tab-badge">{traceTurns.length}</span>}
          </button>
          {(sidebarTab === "facts" || sidebarTab === "pending") && (
            <button
              className="icon-button"
              title={sidebarTab === "facts" ? "Refresh facts" : "Refresh pending facts"}
              onClick={() =>
                sidebarTab === "facts"
                  ? setFactsRefreshKey((k) => k + 1)
                  : setPendingFactsRefreshKey((k) => k + 1)
              }
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
          ) : sidebarTab === "pending" ? (
            selectedTenantId ? (
              <PendingFacts
                key={selectedTenantId}
                idToken={idToken}
                tenantId={selectedTenantId}
                refreshKey={pendingFactsRefreshKey}
                onCountChange={setPendingFactsCount}
                onApproved={() => setFactsRefreshKey((k) => k + 1)}
              />
            ) : (
              <p className="sidebar-empty">Select a project to see facts awaiting review.</p>
            )
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
            onAuthFailed={handleAuthFailed}
            onApplied={() => {
              refreshTenantsQuietly();
              setFactsRefreshKey((k) => k + 1);
            }}
          />
        </div>
      </main>
    </div>
  );
}

export default App;
