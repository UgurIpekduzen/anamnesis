import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

import "@testing-library/jest-dom/vitest";

// Without `globals: true` (see vite.config.ts), Testing Library's own
// auto-cleanup never registers — it looks for a global `afterEach`, which
// only vitest's globals mode provides. Without this, a later test's render
// finds elements a previous test's render left in the document.
afterEach(cleanup);
