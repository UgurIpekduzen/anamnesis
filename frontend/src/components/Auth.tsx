import { useEffect, useRef } from "react";

import { GOOGLE_CLIENT_ID } from "../config";

// Minimal shape of the Google Identity Services global — GIS doesn't
// ship first-party types, and pulling in a whole @types package for
// this one object felt heavier than it's worth.
declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: { client_id: string; callback: (resp: { credential: string }) => void }) => void;
          renderButton: (parent: HTMLElement, options: { theme: string; size: string }) => void;
          prompt: () => void;
        };
      };
    };
  }
}

interface Props {
  onSignIn: (idToken: string) => void;
}

// Re-prompts in the background well before a token's ~1 hour lifetime
// runs out, so the user is (usually) never asked to click "Sign in"
// again mid-session — see APPCE-54 for the tradeoffs behind this.
const SILENT_REFRESH_INTERVAL_MS = 50 * 60 * 1000;

function Auth({ onSignIn }: Props) {
  const buttonRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let refreshInterval: ReturnType<typeof setInterval> | undefined;

    // The GIS <script> tag is async/defer, so it may not have run yet
    // when this component mounts — poll briefly instead of assuming
    // window.google is already there.
    const readyCheck = setInterval(() => {
      if (!window.google || !buttonRef.current) return;
      clearInterval(readyCheck);

      window.google.accounts.id.initialize({
        client_id: GOOGLE_CLIENT_ID,
        callback: (response) => onSignIn(response.credential),
      });
      window.google.accounts.id.renderButton(buttonRef.current, { theme: "outline", size: "large" });

      refreshInterval = setInterval(() => {
        window.google?.accounts.id.prompt();
      }, SILENT_REFRESH_INTERVAL_MS);
    }, 100);

    return () => {
      clearInterval(readyCheck);
      if (refreshInterval) clearInterval(refreshInterval);
    };
  }, [onSignIn]);

  return <div ref={buttonRef} />;
}

export default Auth;
