/**
 * Build-time configuration (Vite env vars; see .env.example at the repo root).
 *
 * VITE_API_BASE_URL — backend origin when the UI is hosted elsewhere (e.g. UI on
 *   Vercel, API on Cloud Run). Empty = same origin (nginx/ingress route /api).
 */
const env = import.meta.env;

export const API_BASE = (env.VITE_API_BASE_URL ?? "").replace(/\/+$/, "");
export const LANDING_URL = env.VITE_LANDING_URL || "https://likhithv02.github.io/Customer-Support-Agent/";
export const REPO_URL = env.VITE_REPO_URL || "https://github.com/LikhithV02/Customer-Support-Agent";

export const apiUrl = (path: string) => `${API_BASE}${path}`;
