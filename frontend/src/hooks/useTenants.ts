import { useEffect, useRef, useState, type MutableRefObject } from "react";

import { ForbiddenError, listTenants, type Tenant } from "../api";
import { useRefreshKey } from "./useRefreshKey";

// The signed-in user's projects and which one is selected. `userId` is the
// account (not the token, which is refreshed silently about hourly): the list
// is reloaded, and the selection reset, only when the account changes.
//
// `onForbidden` is called when the server says this account isn't allowed in
// at all: showing "couldn't load" with a Retry would be wrong.
export function useTenants(
  idTokenRef: MutableRefObject<string | null>,
  userId: string | null,
  onForbidden: () => void,
) {
  const onForbiddenRef = useRef(onForbidden);
  onForbiddenRef.current = onForbidden;
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [selectedTenantId, setSelectedTenantId] = useState<string | null>(null);
  const [error, setError] = useState(false);
  const [reloadKey, reload] = useRefreshKey();
  // Set by TenantSelector right before a reload it triggered itself (e.g.
  // just created a project) — picked up once the fresh list lands, since
  // the list fetch below is async and would otherwise overwrite a
  // synchronous selection with its own fetched[0] fallback.
  const pendingSelectRef = useRef<string | null>(null);
  // Counts project-list requests so a late answer to an older one is dropped
  // (a quiet refresh must never overwrite a newer list or another account's).
  const requestRef = useRef(0);

  // Re-read the project list without touching the selection, unlike the
  // effect below (which resets everything). Used after the assistant links a
  // GitHub repo or Jira key, so the project card shows it.
  function refreshQuietly() {
    const token = idTokenRef.current;
    if (!token) return;
    const request = ++requestRef.current;
    listTenants(token)
      .then((fetched) => {
        if (request === requestRef.current) setTenants(fetched);
      })
      .catch(() => {});
  }

  useEffect(() => {
    if (!userId || !idTokenRef.current) return;
    requestRef.current++;
    // Clear immediately (not just on the fetch resolving) so Chat/Facts
    // — gated on selectedTenantId — briefly unmount instead of running
    // a moment longer against the previous account's stale tenant_id
    // while the new account's list is still loading (matters most for
    // "Change account", which swaps idToken without a full page reset).
    // Keyed on the account, not the token: a plain token refresh must not
    // reset the selected project or throw away the Trace.
    setTenants([]);
    setSelectedTenantId(null);
    setError(false);

    // Ignore a response that lands after the token changed (or after a
    // retry) — it belongs to a request nobody is waiting on anymore.
    let cancelled = false;
    listTenants(idTokenRef.current)
      .then((fetched) => {
        if (cancelled) return;
        setTenants(fetched);
        const pending = pendingSelectRef.current;
        pendingSelectRef.current = null;
        const preferred = pending && fetched.some((t) => t.tenant_id === pending) ? pending : fetched[0]?.tenant_id;
        setSelectedTenantId(preferred ?? null);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ForbiddenError) onForbiddenRef.current();
        else setError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [idTokenRef, userId, reloadKey]);

  return {
    tenants,
    selectedTenantId,
    selectTenant: setSelectedTenantId,
    error,
    retry: reload,
    // TenantSelector changed the list itself (created, renamed, deleted a
    // project): reload it, and select the new project if there is one.
    changed: (newlySelectedId?: string) => {
      pendingSelectRef.current = newlySelectedId ?? null;
      reload();
    },
    refreshQuietly,
  };
}
