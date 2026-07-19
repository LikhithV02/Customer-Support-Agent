import { useEffect, useRef, useState } from "react";
import {
  fetchConversation,
  fetchConversations,
  subscribeToConversation,
} from "../api";
import ReasoningTimeline from "../components/ReasoningTimeline";
import Markdown from "../components/Markdown";
import type {
  AgentEvent,
  ConversationDetail,
  ConversationSummary,
  StepEvent,
} from "../types";

export default function Admin() {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [live, setLive] = useState(false);
  const timelineRef = useRef<HTMLDivElement>(null);

  async function loadList() {
    try {
      setConversations(await fetchConversations());
    } catch {
      /* ignore transient errors */
    }
  }

  useEffect(() => {
    loadList();
    const t = setInterval(loadList, 4000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    let active = true;
    setLive(false);
    fetchConversation(selectedId).then((d) => {
      if (active) setDetail(d);
    });

    const handle = (event: AgentEvent) => {
      setLive(true);
      if (event.kind === "step") {
        setDetail((d) =>
          d && d.id === selectedId
            ? { ...d, events: mergeStep(d.events, event) }
            : d,
        );
      } else if (event.kind === "message") {
        setDetail((d) =>
          d && d.id === selectedId
            ? {
                ...d,
                messages: [
                  ...d.messages,
                  {
                    id: Date.now(),
                    role: event.role,
                    content: event.content,
                    created_at: new Date().toISOString(),
                  },
                ],
              }
            : d,
        );
      }
    };

    const close = subscribeToConversation(selectedId, handle);
    return () => {
      active = false;
      close();
    };
  }, [selectedId]);

  useEffect(() => {
    timelineRef.current?.scrollTo({ top: timelineRef.current.scrollHeight });
  }, [detail?.events]);

  return (
    <div className="grid h-full grid-cols-[300px_1fr]">
      <aside className="flex flex-col border-r border-slate-800 bg-slate-900/40">
        <div className="border-b border-slate-800 px-4 py-3 text-xs font-semibold uppercase tracking-wide text-slate-500">
          Conversations
        </div>
        <div className="flex-1 overflow-y-auto">
          {conversations.length === 0 && (
            <p className="p-4 text-sm text-slate-500">
              No conversations yet. Start one in the Customer Chat tab.
            </p>
          )}
          {conversations.map((c) => (
            <button
              key={c.id}
              onClick={() => setSelectedId(c.id)}
              className={`block w-full border-b border-slate-800/60 px-4 py-3 text-left transition-colors ${
                selectedId === c.id ? "bg-indigo-500/10" : "hover:bg-slate-800/50"
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-slate-200">
                  {c.customer_name || "Unidentified"}
                </span>
                <span className="text-[11px] text-slate-600">{c.message_count} msgs</span>
              </div>
              <div className="mt-0.5 truncate text-xs text-slate-500">
                {c.last_message || "—"}
              </div>
              <div className="mt-0.5 font-mono text-[10px] text-slate-600">{c.id}</div>
            </button>
          ))}
        </div>
      </aside>

      {!detail ? (
        <div className="flex items-center justify-center text-sm text-slate-500">
          Select a conversation to inspect the agent's reasoning.
        </div>
      ) : (
        <div className="grid min-h-0 grid-cols-2">
          <section className="flex min-h-0 flex-col border-r border-slate-800">
            <div className="border-b border-slate-800 px-5 py-3">
              <div className="text-sm font-semibold text-slate-200">Transcript</div>
              <div className="text-xs text-slate-500">
                {detail.customer_name ? `Customer: ${detail.customer_name}` : "Unidentified customer"}
              </div>
            </div>
            <div className="flex-1 space-y-3 overflow-y-auto p-5">
              {detail.messages.map((m) => (
                <div
                  key={m.id}
                  className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
                >
                  <div
                    className={`max-w-[90%] rounded-xl px-3 py-2 text-sm ${
                      m.role === "user"
                        ? "whitespace-pre-wrap bg-indigo-500/90 text-white"
                        : "border border-slate-800 bg-slate-900 text-slate-200"
                    }`}
                  >
                    {m.role === "user" ? m.content : <Markdown>{m.content}</Markdown>}
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section className="flex min-h-0 flex-col">
            <div className="flex items-center justify-between border-b border-slate-800 px-5 py-3">
              <div className="text-sm font-semibold text-slate-200">Agent Reasoning</div>
              {live && (
                <span className="flex items-center gap-1.5 rounded-full bg-rose-500/15 px-2 py-0.5 text-[11px] font-semibold text-rose-300">
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-rose-400" />
                  LIVE
                </span>
              )}
            </div>
            <div ref={timelineRef} className="flex-1 overflow-y-auto p-5">
              <ReasoningTimeline steps={detail.events} />
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

function mergeStep(events: StepEvent[], step: StepEvent): StepEvent[] {
  if (events.some((e) => e.id === step.id)) return events;
  return [...events, step];
}
