import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In Docker, nginx serves the build and proxies /api to the backend (same origin).
// For local `npm run dev`, proxy /api to the backend on :8000.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
