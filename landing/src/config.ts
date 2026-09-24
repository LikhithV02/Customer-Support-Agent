/**
 * Edit these for your own deployment. The two URLs can also be injected at
 * build time (GitHub repo variables → .github/workflows/pages.yml).
 */
export const APP_URL = import.meta.env.VITE_APP_URL || "";
/** Backend origin, pinged on page load so a scaled-to-zero instance wakes up early. */
export const API_URL = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/+$/, "");

export const REPO_URL = "https://github.com/LikhithV02/Customer-Support-Agent";

export const AUTHOR = {
  name: "LikhithV02", // your name as it should appear in the footer
  github: "https://github.com/LikhithV02",
  linkedin: "", // e.g. https://www.linkedin.com/in/<you>
  email: "", // shown as a mailto link when set
};
