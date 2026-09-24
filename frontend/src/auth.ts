/**
 * Where the widget gets its identity.
 *
 * In production the host site (which already knows who is logged in) issues a
 * short-lived signed JWT and hands it to the widget, either:
 *   - by defining `window.ACME_SUPPORT_TOKEN` before the bundle loads, or
 *   - via `postMessage({ type: "acme-support-token", token })` from a parent
 *     window whose origin is listed in VITE_TRUSTED_PARENT_ORIGINS.
 * The backend verifies the token; the chat never asks the user who they are.
 *
 * In local dev (AUTH_MODE=dev) the UI can mint tokens via /api/dev/token.
 */

export type Role = "customer" | "admin";

declare global {
  interface Window {
    ACME_SUPPORT_TOKEN?: string;
    ACME_ADMIN_TOKEN?: string;
  }
}

const KEYS: Record<Role, string> = {
  customer: "acme.customerToken",
  admin: "acme.adminToken",
};

const listeners = new Set<() => void>();

function read(key: string): string | null {
  try {
    return sessionStorage.getItem(key);
  } catch {
    return null;
  }
}

export function getToken(role: Role): string | null {
  const injected = role === "customer" ? window.ACME_SUPPORT_TOKEN : window.ACME_ADMIN_TOKEN;
  return injected || read(KEYS[role]);
}

export function setToken(role: Role, token: string | null): void {
  try {
    if (token) sessionStorage.setItem(KEYS[role], token);
    else sessionStorage.removeItem(KEYS[role]);
  } catch {
    /* storage unavailable (private mode) — keep going without persistence */
  }
  if (role === "customer") window.ACME_SUPPORT_TOKEN = token ?? undefined;
  else window.ACME_ADMIN_TOKEN = token ?? undefined;
  listeners.forEach((fn) => fn());
}

export function onTokenChange(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

const trustedOrigins = (import.meta.env.VITE_TRUSTED_PARENT_ORIGINS ?? "")
  .split(",")
  .map((o: string) => o.trim())
  .filter(Boolean);

window.addEventListener("message", (e: MessageEvent) => {
  if (!trustedOrigins.includes(e.origin)) return;
  const data = e.data as { type?: string; token?: string; role?: Role };
  if (data?.type === "acme-support-token" && typeof data.token === "string") {
    setToken(data.role === "admin" ? "admin" : "customer", data.token);
  }
});

/** Dev only: mint a token from the backend's /api/dev/token endpoint. */
export async function devLogin(role: Role, customerId?: string): Promise<void> {
  const res = await fetch("/api/dev/token", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(role === "admin" ? { admin: true } : { customer_id: customerId }),
  });
  if (!res.ok) throw new Error(`dev login failed: ${res.status}`);
  setToken(role, (await res.json()).token);
}

export async function devCustomers(): Promise<{ id: string; name: string; email: string }[] | null> {
  try {
    const res = await fetch("/api/dev/customers");
    return res.ok ? res.json() : null;
  } catch {
    return null;
  }
}
