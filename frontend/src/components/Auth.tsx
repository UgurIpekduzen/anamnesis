import { useEffect, useRef } from "react";

import { whenGoogleReady } from "../googleAuth";

// Assumes initGoogleAuth() has already been called at the app level
// (see App.tsx) — this component only renders the button.
function Auth() {
  const buttonRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    return whenGoogleReady(() => {
      if (buttonRef.current) {
        window.google!.accounts.id.renderButton(buttonRef.current, { theme: "outline", size: "large" });
      }
    });
  }, []);

  return <div ref={buttonRef} />;
}

export default Auth;
