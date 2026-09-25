import { useEffect, useState, type MutableRefObject } from "react";

import { getGithubConnection, getJiraConnection, type JiraConnection } from "../api";

// Whether the user's GitHub/Jira accounts are connected (APPCE-105) — null
// until known. Re-read when the account changes and whenever `reloadKey`
// changes (Settings closing, where they get connected or disconnected).
export function useConnections(idTokenRef: MutableRefObject<string | null>, userId: string | null, reloadKey: number) {
  const [githubConnected, setGithubConnected] = useState<boolean | null>(null);
  const [jira, setJira] = useState<JiraConnection | null>(null);

  useEffect(() => {
    if (!userId || !idTokenRef.current) return;
    let cancelled = false;
    // Two independent lookups: one failing must not hide the other. A
    // failure leaves the status unknown (no warning), not "disconnected".
    getGithubConnection(idTokenRef.current)
      .then((c) => !cancelled && setGithubConnected(c.connected))
      .catch(() => !cancelled && setGithubConnected(null));
    getJiraConnection(idTokenRef.current)
      .then((c) => !cancelled && setJira(c))
      .catch(() => !cancelled && setJira(null));
    return () => {
      cancelled = true;
    };
  }, [idTokenRef, userId, reloadKey]);

  return { githubConnected, jira };
}
