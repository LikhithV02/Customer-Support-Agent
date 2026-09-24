import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Served from GitHub Pages at https://<user>.github.io/<repo>/, so assets need
// the repo path as their base. Override with LANDING_BASE (e.g. "/" for a
// custom domain).
export default defineConfig({
  base: process.env.LANDING_BASE ?? "/Customer-Support-Agent/",
  plugins: [react()],
});
