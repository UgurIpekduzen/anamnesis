import { GOOGLE_CLIENT_ID } from "./config";

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
          disableAutoSelect: () => void;
        };
      };
    };
  }
}

// The GIS <script> tag is async/defer, so window.google may not exist
// yet when a component mounts — poll briefly instead of assuming it's
// already there. fn may return its own cleanup (e.g. an interval to
// clear); both it and the readiness poll are cleaned up together.
export function whenGoogleReady(fn: () => (() => void) | void): () => void {
  let innerCleanup: (() => void) | void;
  const interval = setInterval(() => {
    if (!window.google) return;
    clearInterval(interval);
    innerCleanup = fn();
  }, 100);
  return () => {
    clearInterval(interval);
    innerCleanup?.();
  };
}

// Called once at the app's top level (see App.tsx) so the callback stays
// wired even after the sign-in screen unmounts — needed for both the
// background silent-refresh prompt and "Change account".
export function initGoogleAuth(onCredential: (idToken: string) => void): void {
  window.google!.accounts.id.initialize({
    client_id: GOOGLE_CLIENT_ID,
    callback: (response) => onCredential(response.credential),
  });
}
