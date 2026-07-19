import { useEffect, useRef, useState } from "react";
import { streamChat } from "../api";
import ReasoningTimeline from "../components/ReasoningTimeline";
import Markdown from "../components/Markdown";
import type { AgentEvent, ChatMessage, StepEvent } from "../types";

const SAMPLE_PROMPTS = [
  "Hi, my email is alice@example.com and I'd like a refund for order ORD-1001.",
  "I'm carol@example.com — I want to return my TV, order ORD-1003.",
  "This is bob@example.com, refund my t-shirt ORD-1002 please.",
];

export default function Chat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [steps, setSteps] = useState<StepEvent[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, steps]);

  async function send(text: string) {
    if (!text.trim() || streaming) return;
    setMessages((m) => [...m, { role: "user", content: text }]);
    setInput("");
    setSteps([]);
    setStreaming(true);

    const handle = (event: AgentEvent) => {
      switch (event.kind) {
        case "conversation":
          setConversationId(event.conversation_id);
          break;
        case "step":
          setSteps((s) => [...s, event]);
          break;
        case "message":
          setMessages((m) => [...m, { role: "assistant", content: event.content }]);
          break;
        case "error":
          setMessages((m) => [
            ...m,
            { role: "assistant", content: `⚠️ ${event.message}` },
          ]);
          break;
      }
    };

    try {
      await streamChat(text, conversationId, handle);
    } catch (err) {
      setMessages((m) => [
        ...m,
        { role: "assistant", content: `⚠️ ${(err as Error).message}` },
      ]);
    } finally {
      setStreaming(false);
    }
  }

  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col px-4">
      <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto py-6">
        {messages.length === 0 && (
          <div className="mt-10 text-center">
            <h2 className="text-lg font-semibold text-slate-200">
              How can I help with your refund today?
            </h2>
            <p className="mt-1 text-sm text-slate-500">
              I can look up your orders and process eligible refunds.
            </p>
            <div className="mt-6 space-y-2">
              {SAMPLE_PROMPTS.map((p) => (
                <button
                  key={p}
                  onClick={() => send(p)}
                  className="block w-full rounded-lg border border-slate-800 bg-slate-900/50 px-4 py-2.5 text-left text-sm text-slate-300 transition-colors hover:border-indigo-500/50 hover:bg-slate-800"
                >
                  {p}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => (
          <div
            key={i}
            className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm ${
                m.role === "user"
                  ? "whitespace-pre-wrap bg-indigo-500 text-white"
                  : "border border-slate-800 bg-slate-900 text-slate-200"
              }`}
            >
              {m.role === "user" ? m.content : <Markdown>{m.content}</Markdown>}
            </div>
          </div>
        ))}

        {streaming && (
          <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
            <div className="mb-3 flex items-center gap-2 text-xs font-medium text-indigo-300">
              <span className="h-2 w-2 animate-pulse rounded-full bg-indigo-400" />
              Agent is working… (checking your order against the refund policy)
            </div>
            <ReasoningTimeline steps={steps} />
          </div>
        )}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
        className="border-t border-slate-800 py-4"
      >
        <div className="flex items-end gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send(input);
              }
            }}
            rows={1}
            placeholder="Type your message…"
            className="flex-1 resize-none rounded-xl border border-slate-700 bg-slate-900 px-4 py-3 text-sm text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none"
          />
          <button
            type="submit"
            disabled={streaming || !input.trim()}
            className="rounded-xl bg-indigo-500 px-5 py-3 text-sm font-semibold text-white transition-colors hover:bg-indigo-400 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Send
          </button>
        </div>
      </form>
    </div>
  );
}
