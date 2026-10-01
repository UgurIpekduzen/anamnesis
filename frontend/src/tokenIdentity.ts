// Who a Google ID token belongs to. The token itself changes every ~50
// minutes when it is silently refreshed, but its `sub` claim — Google's
// stable id for the account — does not, so this is what tells "the same
// user with a fresh token" apart from "a different account".
export function tokenSubject(idToken: string | null): string | null {
  if (!idToken) return null;
  try {
    // JWT payloads are base64url; atob() wants plain base64 with padding.
    const base64 = idToken.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4);
    const sub = JSON.parse(atob(padded)).sub;
    // A token we can't read is treated as its own identity, which falls
    // back to the old behaviour (reset whenever the token changes) rather
    // than to never resetting at all.
    return typeof sub === "string" && sub ? sub : idToken;
  } catch {
    return idToken;
  }
}
