import { GOOGLE_CLIENT_ID } from "./config";

// Minimal shape of the Google Identity Services global — GIS doesn't
// ship first-party types, and pulling in a whole @types package for
// this one object felt heavier than it's worth.
//
// A moment's outcome, as GIS reports it to prompt()'s optional callback:
// whether the One Tap UI was shown at all, and if not (or if the user
// closed it), why. Whether prompt() itself uses the
// legacy popup flow or FedCM is entirely up to the browser — there is no
// config flag for it (use_fedcm_for_prompt exists in older docs but is
// now ignored) — and under FedCM the display-related methods
// (isDisplayMoment/isDisplayed/isNotDisplayed/getNotDisplayedReason) are
// dropped from the notification object for privacy, so every method here
// is optional and describePromptMoment below only calls what exists.
interface PromptMomentNotification {
  isDisplayMoment?: () => boolean;
  isNotDisplayed?: () => boolean;
  getNotDisplayedReason?: () => string;
  isSkippedMoment?: () => boolean;
  getSkippedReason?: () => string;
  isDismissedMoment?: () => boolean;
  getDismissedReason?: () => string;
}

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: {
            client_id: string;
            callback: (resp: { credential: string }) => void;
            auto_select?: boolean;
            use_fedcm_for_button?: boolean;
          }) => void;
          renderButton: (parent: HTMLElement, options: { theme: string; size: string }) => void;
          prompt: (momentListener?: (notification: PromptMomentNotification) => void) => void;
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
//
// auto_select lets prompt() return a fresh token with no UI shown at all
// when there is exactly one Google session that already approved this
// app — without it, prompt() always shows the One Tap UI and waits for a
// click, so the ~50-minute background refresh timer (App.tsx) was never
// actually silent.
// use_fedcm_for_button opts the rendered Sign In button into Chrome's
// native FedCM flow where supported (M125+ desktop, M128+ Android); GIS
// falls back to the classic button on browsers that don't support it, so
// this is safe to set unconditionally. It only affects the button — the
// background prompt() refresh has no such switch (see the interface
// comment above).
export function initGoogleAuth(onCredential: (idToken: string) => void): void {
  window.google!.accounts.id.initialize({
    client_id: GOOGLE_CLIENT_ID,
    callback: (response) => onCredential(response.credential),
    auto_select: true,
    use_fedcm_for_button: true,
  });
}

// What happened to a prompt() call, boiled down to one word, for the
// background refresh to log — never the credential or anything from it.
export function describePromptMoment(notification: PromptMomentNotification): string {
  if (notification.isDisplayMoment?.()) return "displayed";
  if (notification.isNotDisplayed?.())
    return `not_displayed:${notification.getNotDisplayedReason?.() ?? "?"}`;
  if (notification.isSkippedMoment?.())
    return `skipped:${notification.getSkippedReason?.() ?? "?"}`;
  if (notification.isDismissedMoment?.())
    return `dismissed:${notification.getDismissedReason?.() ?? "?"}`;
  return "unknown";
}
