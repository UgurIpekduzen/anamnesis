import { useEffect, useMemo, useReducer, useRef, useState } from "react";

import "./App.css";
import AccountMenu from "./components/AccountMenu";
import Auth from "./components/Auth";
import Chat from "./components/Chat";
import Facts from "./components/Facts";
import PendingFacts from "./components/PendingFacts";
import ProjectLinks from "./components/ProjectLinks";
import StatusPanel from "./components/StatusPanel";
import SettingsDialog from "./components/SettingsDialog";
import TenantSelector from "./components/TenantSelector";
import TracePanel from "./components/TracePanel";
import UsageCounter from "./components/UsageCounter";
import { describePromptMoment, initGoogleAuth, whenGoogleReady } from "./googleAuth";
import { useConnections } from "./hooks/useConnections";
import { useRefreshKey } from "./hooks/useRefreshKey";
import { useResizableSidebar } from "./hooks/useResizableSidebar";
import { useTenants } from "./hooks/useTenants";
import { tokenSubject } from "./tokenIdentity";
import { traceReducer, type ChatEvent } from "./trace";

type SidebarTab = "facts" | "pending" | "status" | "trace";

// Re-prompts in the background well before a token's ~1 hour lifetime
// runs out, so the user is (usually) never asked to sign in again
// mid-session — see APPCE-54 for the tradeoffs behind this. Lives at
// the app level (not Auth.tsx) since it must keep running after the
// sign-in screen unmounts.
const SILENT_REFRESH_INTERVAL_MS = 50 * 60 * 1000;

// When to re-read the facts after a fact was published: the write goes
// through Pub/Sub, so it usually lands within a couple of seconds.
const FACTS_RETRY_DELAYS_MS = [1500, 4000, 8000];

// The notice for the sign-in screen has to survive the page reload
// handleAccountNotAllowed does, so it is parked here for a moment.
const SIGN_IN_NOTICE_KEY = "anamnesis.signInNotice";
const LAST_RELOAD_KEY = "anamnesis.accountNotAllowedReloadAt";
// A reload that lands on the same refused account again must not reload
// again, or the page would loop.
const RELOAD_LOOP_WINDOW_MS = 30_000;
const ACCOUNT_NOT_ALLOWED_NOTICE =
  "This account isn't invited to Anamnesis yet. Ask the owner to add it, or sign in with a different account.";

// A project-specific address (not the owner's personal one) for access
// requests. mailto: puts it in the page's source, so it will be public once
// the repo is; it exists only to receive this kind of request.
const CONTACT_EMAIL = "anamnesis.project@gmail.com";
const CONTACT_MAILTO =
  `mailto:${CONTACT_EMAIL}` +
  "?subject=" +
  encodeURIComponent("Anamnesis access request") +
  "&body=" +
  encodeURIComponent("Google account email you'd like invited:\n\n");

function takeParkedNotice(): string | null {
  try {
    const notice = sessionStorage.getItem(SIGN_IN_NOTICE_KEY);
    sessionStorage.removeItem(SIGN_IN_NOTICE_KEY);
    return notice;
  } catch {
    return null; // storage can be blocked; the notice is a courtesy
  }
}

function App() {
  const [idToken, setIdToken] = useState<string | null>(null);
  const [factsRefreshKey, bumpFacts] = useRefreshKey();
  const [sidebarTab, setSidebarTab] = useState<SidebarTab>("facts");
  const [traceTurns, dispatchTrace] = useReducer(traceReducer, []);
  const [connectionsReloadKey, reloadConnections] = useRefreshKey();
  const [usageRefreshKey, bumpUsage] = useRefreshKey();
  const [pendingFactsRefreshKey, bumpPendingFacts] = useRefreshKey();
  const [pendingFactsCount, setPendingFactsCount] = useState(0);
  const [statusRefreshKey, bumpStatus] = useRefreshKey();
  const sidebar = useResizableSidebar();
  const [googleReady, setGoogleReady] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  // Why the user landed back on the sign-in screen (the chat socket was
  // rejected, APPCE-69, or the account isn't allowed in, APPCE-114).
  const [signInNotice, setSignInNotice] = useState<string | null>(takeParkedNotice);

  // The token is refreshed silently about every 50 minutes; the account it
  // belongs to is what decides whether the project list is stale.
  const userId = useMemo(() => tokenSubject(idToken), [idToken]);
  const idTokenRef = useRef(idToken);
  idTokenRef.current = idToken;
  const { githubConnected, jira: jiraConnection } = useConnections(idTokenRef, userId, connectionsReloadKey);
  const {
    tenants,
    selectedTenantId,
    selectTenant,
    error: tenantsError,
    retry: retryTenants,
    changed: tenantsChanged,
    refreshQuietly: refreshTenantsQuietly,
  } = useTenants(idTokenRef, userId, handleAccountNotAllowed);
  const selectedTenant = tenants.find((t) => t.tenant_id === selectedTenantId) ?? null;

  // Pending re-fetches of the facts list after a fact was published.
  const factsRetryTimersRef = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(() => {
    return whenGoogleReady(() => {
      initGoogleAuth((token) => {
        setSignInNotice(null);
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

  // Everything Chat reports funnels through here: the usage counter and
  // the facts list refresh off it, and the Trace tab is built from it.
  function handleChatEvent(event: ChatEvent) {
    dispatchTrace({ ...event, at: Date.now() });
    // On send, and again when the turn ends: the server counts the message
    // alongside the model call, so the count read right after sending can
    // still be the old one (APPCE-72).
    if (event.type === "sent" || event.type === "answered" || event.type === "failed") {
      bumpUsage();
    }
    // A fact the agent just recorded lands asynchronously (Pub/Sub), so a
    // single refetch when the turn ends can beat it. Ask again a few times
    // shortly after; the Facts refresh button stays as the last resort.
    if (event.type === "tool_result" && event.name === "publish_fact") {
      factsRetryTimersRef.current.forEach(clearTimeout);
      factsRetryTimersRef.current = FACTS_RETRY_DELAYS_MS.map((delay) =>
        setTimeout(() => bumpFacts(), delay),
      );
    }
    if (event.type === "answered") {
      bumpFacts();
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
    setSignInNotice("Your session ended. Please sign in again.");
    setIdToken(null);
  }

  // The server refuses this account outright (not on the allowlist). Unlike
  // handleAuthFailed, auto-select must go: it would silently sign the same
  // account straight back in, and the user could never pick another one.
  // The page is reloaded too: after this, Google's sign-in button stopped
  // reacting to clicks until the page was refreshed, so start it fresh.
  function handleAccountNotAllowed() {
    window.google?.accounts.id.disableAutoSelect();
    let reloadedJustNow = false;
    try {
      reloadedJustNow = Date.now() - Number(sessionStorage.getItem(LAST_RELOAD_KEY) ?? 0) < RELOAD_LOOP_WINDOW_MS;
      if (!reloadedJustNow) {
        sessionStorage.setItem(LAST_RELOAD_KEY, String(Date.now()));
        sessionStorage.setItem(SIGN_IN_NOTICE_KEY, ACCOUNT_NOT_ALLOWED_NOTICE);
      }
    } catch {
      // Without storage a reload would lose the explanation: just show it.
      reloadedJustNow = true;
    }
    if (reloadedJustNow) {
      setSignInNotice(ACCOUNT_NOT_ALLOWED_NOTICE);
      setIdToken(null);
    } else {
      window.location.reload();
    }
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
          {signInNotice && (
            <p className="session-expired">
              {signInNotice}
              {signInNotice === ACCOUNT_NOT_ALLOWED_NOTICE && (
                <>
                  {" "}
                  <a href={CONTACT_MAILTO}>Request access</a>.
                  <br />
                  <span className="signin-hint">
                    We'll only use this email to consider your request.
                  </span>
                </>
              )}
            </p>
          )}
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
            reloadConnections();
            // The Facts tab lists groups in the user's category order.
            bumpFacts();
          }}
          // The warning threshold lives in Settings, so the counter in the
          // sidebar has to refetch to pick up a new one.
          onSaved={() => bumpUsage()}
        />
      )}

      <aside className="sidebar" style={{ width: sidebar.width }}>
        <UsageCounter idToken={idToken} refreshKey={usageRefreshKey} />
        <TenantSelector
          idToken={idToken}
          tenants={tenants}
          selectedId={selectedTenantId}
          onSelect={selectTenant}
          error={tenantsError}
          onRetry={retryTenants}
          onChanged={tenantsChanged}
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
            className={`tab ${sidebarTab === "status" ? "active" : ""}`}
            onClick={() => setSidebarTab("status")}
          >
            Status
          </button>
          <button
            className={`tab ${sidebarTab === "trace" ? "active" : ""}`}
            onClick={() => setSidebarTab("trace")}
          >
            Trace
            {traceTurns.length > 0 && <span className="tab-badge">{traceTurns.length}</span>}
          </button>
          {sidebarTab !== "trace" && (
            <button
              className="icon-button"
              title={
                sidebarTab === "facts"
                  ? "Refresh facts"
                  : sidebarTab === "pending"
                    ? "Refresh pending facts"
                    : "Refresh status"
              }
              onClick={() => (sidebarTab === "facts" ? bumpFacts() : sidebarTab === "pending" ? bumpPendingFacts() : bumpStatus())}
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
          ) : sidebarTab === "status" ? (
            selectedTenantId ? (
              // Remounted when a link changes, so it reads the new repo or key.
              <StatusPanel
                key={`${selectedTenantId}:${selectedTenant?.jira_project_key}:${selectedTenant?.github_repo}`}
                idToken={idToken}
                tenantId={selectedTenantId}
                refreshKey={statusRefreshKey}
              />
            ) : (
              <p className="sidebar-empty">Select a project to see what is open.</p>
            )
          ) : sidebarTab === "pending" ? (
            selectedTenantId ? (
              <PendingFacts
                key={selectedTenantId}
                idToken={idToken}
                tenantId={selectedTenantId}
                refreshKey={pendingFactsRefreshKey}
                onCountChange={setPendingFactsCount}
                onApproved={() => bumpFacts()}
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

      <div className="resize-handle" onMouseDown={sidebar.startResize} />

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
              bumpFacts();
            }}
          />
        </div>
      </main>
    </div>
  );
}

export default App;
