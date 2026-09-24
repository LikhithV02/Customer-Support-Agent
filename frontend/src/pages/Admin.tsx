import clsx from "clsx";
import {
  ArrowLeft,
  CheckCircle2,
  Coins,
  MessagesSquare,
  Search,
  ShieldAlert,
  UserRoundCog,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  fetchConversation,
  fetchConversations,
  fetchStats,
  friendlyError,
  subscribeToConversation,
} from "../api";
import { getToken, onTokenChange } from "../auth";
import Markdown from "../components/Markdown";
import ReasoningTimeline from "../components/ReasoningTimeline";
import { Badge, LiveDot, Skeleton } from "../components/ui";
import { useMeta } from "../lib/meta";
import type { Tone } from "../lib/outcome";
import type {
  AdminStats,
  AgentEvent,
  ConversationDetail,
  ConversationSummary,
  StepEvent,
} from "../types";

function Kpi({
  icon: Icon,
  label,
  value,
  tone = "neutral",
}: {
  icon: LucideIcon;
  label: string;
  value: number | string | undefined;
  tone?: Tone;
}) {
  const color = {
    ok: "text-ok bg-ok/10",
    bad: "text-bad bg-bad/10",
    warn: "text-warn bg-warn/10",
    info: "text-info bg-info/10",
    brand: "text-brand bg-brand/10",
    neutral: "text-muted bg-surface-2",
  }[tone];
  return (
    <div className="flex items-center gap-3 rounded-xl border border-line bg-surface px-3.5 py-3 shadow-sm">
      <span className={clsx("flex h-9 w-9 shrink-0 items-center justify-center rounded-lg", color)}>
        <Icon size={17} />
      </span>
      <div className="min-w-0">
        <div className="truncate text-[11px] font-medium text-subtle">{label}</div>
        <div className="text-lg font-semibold tabular-nums leading-tight">
          {value === undefined ? <Skeleton className="mt-1 h-4 w-10" /> : value}
        </div>
      </div>
    </div>
  );
}

function ago(iso: string): string {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return new Date(iso).toLocaleDateString();
}

export default function Admin() {
  const { meta } = useMeta();
  const [conversations, setConversations] = useState<ConversationSummary[] | null>(null);
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [live, setLive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [hasToken, setHasToken] = useState(Boolean(getToken("admin")));
  const timelineRef = useRef<HTMLDivElement>(null);

  useEffect(() => onTokenChange(() => setHasToken(Boolean(getToken("admin")))), []);

  useEffect(() => {
    if (!hasToken) return;
    let active = true;
    const load = async () => {
      try {
        const [list, s] = await Promise.all([fetchConversations(), fetchStats()]);
        if (!active) return;
        setConversations(list);
        setStats(s);
        setError(null);
        // Open the most recent conversation by default (desktop only).
        setSelectedId((id) => id ?? (window.innerWidth >= 1024 ? list[0]?.id ?? null : null));
      } catch (err) {
        if (active) setError(friendlyError(err));
      }
    };
    load();
    const t = setInterval(load, 5000);
    return () => {
      active = false;
      clearInterval(t);
    };
  }, [hasToken]);

  useEffect(() => {
    if (!selectedId) return;
    let active = true;
    setLive(false);
    setDetail(null);
    fetchConversation(selectedId)
      .then((d) => active && setDetail(d))
      .catch((err) => setError(friendlyError(err)));

    const handle = (event: AgentEvent) => {
      setLive(true);
      if (event.kind === "step") {
        setDetail((d) =>
          d && d.id === selectedId ? { ...d, events: mergeStep(d.events, event) } : d,
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
    timelineRef.current?.scrollTo({ top: timelineRef.current.scrollHeight, behavior: "smooth" });
  }, [detail?.events.length]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!conversations || !q) return conversations;
    return conversations.filter((c) =>
      [c.customer_name, c.customer_id, c.last_message, c.id].some((v) =>
        v?.toLowerCase().includes(q),
      ),
    );
  }, [conversations, query]);

  if (!hasToken) {
    return (
      <div className="flex h-full items-center justify-center px-6 text-center text-sm text-muted">
        Admin sign-in required.
        {meta?.auth_mode === "dev" && " (Local dev: toggle “Admin” in the DEV menu above.)"}
      </div>
    );
  }

  const d = stats?.decisions ?? {};
  const scoped = meta?.auth_mode === "demo";

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-line px-4 py-4 sm:px-5">
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          <div>
            <h1 className="text-base font-semibold">Agent console</h1>
            <p className="text-xs text-subtle">
              {scoped
                ? "What a support lead sees: transcripts and reasoning traces. Your token only shows your own sandbox."
                : "Transcripts, reasoning traces and decisions across all conversations."}
            </p>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
          <Kpi icon={MessagesSquare} label="Conversations" value={stats?.conversations} tone="brand" />
          <Kpi icon={CheckCircle2} label="Approved" value={stats ? d.approved ?? 0 : undefined} tone="ok" />
          <Kpi icon={XCircle} label="Denied" value={stats ? d.denied ?? 0 : undefined} tone="bad" />
          <Kpi icon={UserRoundCog} label="Escalated" value={stats ? d.escalated ?? 0 : undefined} tone="warn" />
          <Kpi icon={ShieldAlert} label="Injection flags" value={stats?.injection_flags} tone="bad" />
          <Kpi icon={Coins} label="LLM tokens" value={stats?.tokens_used.toLocaleString()} tone="info" />
        </div>
      </div>

      <div className="grid min-h-0 flex-1 lg:grid-cols-[300px_1fr]">
        <aside
          className={clsx(
            "min-h-0 flex-col border-r border-line bg-surface/50",
            selectedId ? "hidden lg:flex" : "flex",
          )}
        >
          <div className="border-b border-line p-3">
            <label className="flex items-center gap-2 rounded-lg border border-line bg-surface px-2.5 py-1.5 focus-within:border-brand/60">
              <Search size={14} className="text-subtle" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search conversations"
                aria-label="Search conversations"
                className="w-full bg-transparent text-sm placeholder:text-subtle focus:outline-none focus-visible:ring-0 focus-visible:ring-offset-0"
              />
            </label>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {error && <p className="p-4 text-xs text-bad">{error}</p>}
            {conversations === null && !error && (
              <div className="space-y-2 p-3">
                {[0, 1, 2].map((i) => (
                  <Skeleton key={i} className="h-16" />
                ))}
              </div>
            )}
            {filtered?.length === 0 && (
              <div className="p-6 text-center text-sm text-subtle">
                {query ? "No matches." : "No conversations yet."}
                {!query && (
                  <div className="mt-2">
                    <Link to="/chat" className="font-medium text-brand hover:underline">
                      Start one in the chat
                    </Link>
                  </div>
                )}
              </div>
            )}
            {filtered?.map((c) => (
              <button
                key={c.id}
                onClick={() => setSelectedId(c.id)}
                className={clsx(
                  "block w-full border-b border-line/70 px-4 py-3 text-left transition-colors",
                  selectedId === c.id
                    ? "border-l-2 border-l-brand bg-brand/5"
                    : "hover:bg-surface-2",
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-medium">
                    {c.customer_name || "Unidentified"}
                  </span>
                  <span className="shrink-0 text-[11px] text-subtle">{ago(c.created_at)}</span>
                </div>
                <div className="mt-0.5 truncate text-xs text-muted">{c.last_message || "—"}</div>
                <div className="mt-1 flex items-center gap-2 text-[10px] text-subtle">
                  <span className="font-mono">{c.customer_id}</span>·<span>{c.message_count} msgs</span>
                </div>
              </button>
            ))}
          </div>
        </aside>

        {!selectedId ? (
          <div className="hidden items-center justify-center p-6 text-sm text-subtle lg:flex">
            Select a conversation to inspect the agent's reasoning.
          </div>
        ) : (
          <div className="grid min-h-0 grid-rows-[auto_1fr] md:grid-cols-2 md:grid-rows-1">
            <section className="flex min-h-0 flex-col border-b border-line md:border-b-0 md:border-r">
              <div className="flex items-center gap-2 border-b border-line px-4 py-3">
                <button
                  onClick={() => setSelectedId(null)}
                  className="text-muted hover:text-fg lg:hidden"
                  aria-label="Back to list"
                >
                  <ArrowLeft size={16} />
                </button>
                <div>
                  <div className="text-sm font-semibold">Transcript</div>
                  <div className="text-xs text-subtle">
                    {detail?.customer_name ?? "…"} ·{" "}
                    <span className="font-mono">{detail?.customer_id}</span>
                  </div>
                </div>
              </div>
              <div className="max-h-[40vh] min-h-0 flex-1 space-y-3 overflow-y-auto p-4 md:max-h-none">
                {!detail && <Skeleton className="h-24" />}
                {detail?.messages.map((m) => (
                  <div
                    key={m.id}
                    className={clsx("flex", m.role === "user" ? "justify-end" : "justify-start")}
                  >
                    <div
                      className={clsx(
                        "max-w-[90%] rounded-xl px-3 py-2 text-sm",
                        m.role === "user"
                          ? "whitespace-pre-wrap bg-brand-solid text-white"
                          : "border border-line bg-surface",
                      )}
                    >
                      {m.role === "user" ? m.content : <Markdown>{m.content}</Markdown>}
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <section className="flex min-h-0 flex-col">
              <div className="flex items-center justify-between border-b border-line px-4 py-3">
                <div className="text-sm font-semibold">Reasoning trace</div>
                {live ? (
                  <Badge tone="bad">
                    <LiveDot /> LIVE
                  </Badge>
                ) : (
                  <span className="text-[11px] text-subtle">{detail?.events.length ?? 0} steps</span>
                )}
              </div>
              <div ref={timelineRef} className="min-h-0 flex-1 overflow-y-auto p-4">
                {detail ? <ReasoningTimeline steps={detail.events} /> : <Skeleton className="h-40" />}
              </div>
            </section>
          </div>
        )}
      </div>
    </div>
  );
}

function mergeStep(events: StepEvent[], step: StepEvent): StepEvent[] {
  if (events.some((e) => e.id === step.id)) return events;
  return [...events, step];
}
