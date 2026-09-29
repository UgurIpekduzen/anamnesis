import { useEffect, useState, type MutableRefObject } from "react";

import { getAllowedEmails } from "../api";

// Whether the signed-in account is a Terraform-configured owner — null
// until known, and while unknown the account menu's "Admin" entry stays
// hidden rather than flashing in. getAllowedEmails already
// turns a 403 into null, which is exactly "not an owner" here.
export function useIsOwner(idTokenRef: MutableRefObject<string | null>, userId: string | null) {
  const [isOwner, setIsOwner] = useState<boolean | null>(null);

  useEffect(() => {
    if (!userId || !idTokenRef.current) return;
    let cancelled = false;
    getAllowedEmails(idTokenRef.current)
      .then((allowed) => !cancelled && setIsOwner(allowed !== null))
      .catch(() => !cancelled && setIsOwner(null));
    return () => {
      cancelled = true;
    };
  }, [idTokenRef, userId]);

  return isOwner;
}
