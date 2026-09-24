import { getToken, type Role } from "./auth";
import type { AgentEvent, ConversationDetail, ConversationSummary } from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public retryAfter?: number,
  ) {
    super(message);
  }
}

/** A user-facing message for each failure the backend can return. */
export function friendlyError(err: unknown): string {
  if (err instanceof ApiError) {
    switch (err.status) {
      case 401:
        return "Your session has expired. Please sign in again.";
      case 403:
        return "You don't have access to that.";
      case 404:
        return "That conversation couldn't be found. Please start a new chat.";
      case 409:
        return "I'm still working on your previous message — one moment.";
      case 429:
        return err.message || "You're sending messages too quickly. Please wait a moment.";
      case 503:
        return `We're experiencing high demand. Please try again in ${err.retryAfter ?? 5} seconds.`;
    }
    return err.message;
  }
  return (err as Error)?.message ?? "Something went wrong.";
}

async function request(role: Role, url: string, init: RequestInit = {}): Promise<Response> {
  const token = getToken(role);
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body) headers.set("Content-Type", "application/json");
  const res = await fetch(url, { ...init, headers });
  if (!res.ok) {
    let detail = `request failed: ${res.status}`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* non-JSON error body */
    }
    const retry = Number(res.headers.get("Retry-After")) || undefined;
    throw new ApiError(res.status, detail, retry);
  }
  return res;
}

/**
 * Read Server-Sent Events from a fetch response body. Used instead of
 * EventSource because EventSource can neither POST nor send an
 * Authorization header.
 */
async function readSSE(res: Response, onEvent: (event: AgentEvent) => void): Promise<void> {
  if (!res.body) return;
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const flush = (frame: string) => {
    const data = frame
      .split(/\r?\n/)
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trimStart())
      .join("\n");
    if (data) onEvent(JSON.parse(data) as AgentEvent);
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // SSE frames are separated by a blank line (\n\n or \r\n\r\n).
    const frames = buffer.split(/\r?\n\r?\n/);
    buffer = frames.pop() ?? "";
    for (const frame of frames) flush(frame);
  }
  if (buffer.trim()) flush(buffer);
}

/** Stream a chat turn as the signed-in customer. */
export async function streamChat(
  message: string,
  conversationId: string | null,
  onEvent: (event: AgentEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await request("customer", "/api/chat", {
    method: "POST",
    body: JSON.stringify({ message, conversation_id: conversationId }),
    signal,
  });
  await readSSE(res, onEvent);
}

export async function fetchConversations(): Promise<ConversationSummary[]> {
  return (await request("admin", "/api/conversations?limit=100")).json();
}

export async function fetchConversation(id: string): Promise<ConversationDetail> {
  return (await request("admin", `/api/conversations/${encodeURIComponent(id)}`)).json();
}

/**
 * Subscribe (as admin) to live reasoning events for a conversation. Reconnects
 * with backoff if the stream drops (e.g. a pod is replaced). Returns a closer.
 */
export function subscribeToConversation(
  id: string,
  onEvent: (event: AgentEvent) => void,
): () => void {
  const controller = new AbortController();
  let attempt = 0;

  const connect = async () => {
    while (!controller.signal.aborted) {
      try {
        const res = await request("admin", `/api/conversations/${encodeURIComponent(id)}/stream`, {
          signal: controller.signal,
        });
        attempt = 0;
        await readSSE(res, onEvent);
      } catch (err) {
        if (controller.signal.aborted) return;
        if (err instanceof ApiError && (err.status === 401 || err.status === 403)) return;
      }
      attempt += 1;
      await new Promise((r) => setTimeout(r, Math.min(15000, 500 * 2 ** attempt)));
    }
  };
  void connect();
  return () => controller.abort();
}
