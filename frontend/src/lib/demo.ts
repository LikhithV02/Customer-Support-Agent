import { createDemoSession } from "../api";
import { setToken } from "../auth";
import type { DemoSession } from "../types";

/**
 * Public-demo sandbox (backend AUTH_MODE=demo). The session holds a customer
 * token for chat and a scoped admin token for the agent console, both kept in
 * sessionStorage so a tab reload keeps the sandbox but a new tab starts fresh.
 */
const KEY = "acme.demoSession";

type Stored = DemoSession & { started_at: number };

export function getDemo(): Stored | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return null;
    const s = JSON.parse(raw) as Stored;
    // Tokens expire server-side; drop the sandbox a minute early.
    if (Date.now() > s.started_at + (s.expires_in - 60) * 1000) {
      clearDemo();
      return null;
    }
    return s;
  } catch {
    return null;
  }
}

export async function startDemo(turnstileToken?: string): Promise<Stored> {
  const session = await createDemoSession(turnstileToken);
  const stored: Stored = { ...session, started_at: Date.now() };
  try {
    sessionStorage.setItem(KEY, JSON.stringify(stored));
  } catch {
    /* storage unavailable: tokens still live in memory for this page */
  }
  setToken("admin", session.admin_token);
  setToken("customer", session.token);
  return stored;
}

export function clearDemo(): void {
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
  setToken("admin", null);
  setToken("customer", null);
}
