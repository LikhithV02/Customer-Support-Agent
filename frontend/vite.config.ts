import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In Docker, nginx serves the build and proxies /api to the backend (same origin).
// For local `npm run dev`, proxy /api to the backend on :8000, or to another
// backend with API_PROXY_TARGET (e.g. the Cloud Run demo).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: process.env.API_PROXY_TARGET || "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
