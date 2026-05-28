import type { AgentEvent, ConversationDetail, ConversationSummary } from "./types";

/**
 * Stream a chat turn. POSTs the message and parses the Server-Sent Events from
 * the response body (EventSource can't issue POSTs, so we read the stream
 * manually). `onEvent` is called for every agent event as it arrives.
 */
export async function streamChat(
  message: string,
  conversationId: string | null,
  onEvent: (event: AgentEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, conversation_id: conversationId }),
    signal,
  });
  if (!res.ok || !res.body) {
    throw new Error(`chat request failed: ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const flush = (frame: string) => {
    for (const line of frame.split(/\r?\n/)) {
      if (line.startsWith("data:")) {
        const data = line.slice(5).trim();
        if (data) onEvent(JSON.parse(data) as AgentEvent);
      }
    }
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

export async function fetchConversations(): Promise<ConversationSummary[]> {
  const res = await fetch("/api/conversations");
  if (!res.ok) throw new Error("failed to load conversations");
  return res.json();
}

export async function fetchConversation(id: string): Promise<ConversationDetail> {
  const res = await fetch(`/api/conversations/${id}`);
  if (!res.ok) throw new Error("failed to load conversation");
  return res.json();
}

/** Subscribe to live reasoning events for a conversation. Returns a closer. */
export function subscribeToConversation(
  id: string,
  onEvent: (event: AgentEvent) => void,
): () => void {
  const source = new EventSource(`/api/conversations/${id}/stream`);
  source.onmessage = (e) => {
    if (e.data) onEvent(JSON.parse(e.data) as AgentEvent);
  };
  return () => source.close();
}
