import { useCallback, useState } from "react";

// A counter a component passes down as `refreshKey`: bumping it makes the
// child re-read its data. `bump` keeps the same identity across renders.
export function useRefreshKey(): [key: number, bump: () => void] {
  const [key, setKey] = useState(0);
  const bump = useCallback(() => setKey((k) => k + 1), []);
  return [key, bump];
}
