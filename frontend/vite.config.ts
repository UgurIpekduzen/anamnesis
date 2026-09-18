import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    // Bind to all interfaces so the Vite dev server is reachable from
    // outside the Docker container, not just localhost inside it.
    host: "0.0.0.0",
    port: 5173,
  },
});
