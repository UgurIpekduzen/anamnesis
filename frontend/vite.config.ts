import react from "@vitejs/plugin-react";
// vitest/config re-exports vite's defineConfig with the `test` option typed
// (APPCE-127) — importing from "vite" instead would make `test` below a
// type error, even though it works at runtime.
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    // Bind to all interfaces so the Vite dev server is reachable from
    // outside the Docker container, not just localhost inside it.
    host: "0.0.0.0",
    port: 5173,
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/setupTests.ts",
  },
});
