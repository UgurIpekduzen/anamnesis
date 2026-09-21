import { useEffect, useRef } from "react";

interface Props {
  // True once App.tsx has called initGoogleAuth() — GIS requires
  // initialize() before renderButton() works, and this component has
  // no way to know that happened on its own.
  ready: boolean;
}

function Auth({ ready }: Props) {
  const buttonRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ready || !buttonRef.current) return;
    window.google!.accounts.id.renderButton(buttonRef.current, { theme: "outline", size: "large" });
  }, [ready]);

  return <div ref={buttonRef} />;
}

export default Auth;
