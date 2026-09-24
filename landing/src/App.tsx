import clsx from "clsx";
import {
  ArrowRight,
  Boxes,
  Eye,
  Gauge,
  Github,
  KeyRound,
  Linkedin,
  Lock,
  Mail,
  Moon,
  Scale,
  ShieldAlert,
  Sun,
  Timer,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import Architecture from "./Architecture";
import { API_URL, APP_URL, AUTHOR, REPO_URL } from "./config";

const DEMO_HREF = APP_URL || REPO_URL;
const asset = (p: string) => `${import.meta.env.BASE_URL}${p}`;

/* ------------------------------------------------------------------------ */

function useTheme(): [boolean, () => void] {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"));
  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
  }, [dark]);
  return [
    dark,
    () =>
      setDark((d) => {
        try {
          localStorage.setItem("acme.theme", d ? "light" : "dark");
        } catch {
          /* ignore */
        }
        return !d;
      }),
  ];
}

type Status = "checking" | "waking" | "online" | "offline";

/**
 * Ping the backend on page load. Besides showing a status pill, this wakes a
 * scaled-to-zero Cloud Run instance while the visitor is still reading, so
 * the demo is warm by the time they click through. `no-cors` because the
 * pill only needs to know that *something* answered.
 */
function useBackendStatus(): Status {
  const [status, setStatus] = useState<Status>(API_URL ? "checking" : "offline");
  useEffect(() => {
    if (!API_URL) return;
    let done = false;
    const slow = setTimeout(() => !done && setStatus("waking"), 2500);
    const ping = async (attempt: number): Promise<void> => {
      try {
        await fetch(`${API_URL}/api/health/live`, { mode: "no-cors", cache: "no-store" });
        done = true;
        setStatus("online");
      } catch {
        if (attempt < 3) return ping(attempt + 1);
        done = true;
        setStatus("offline");
      }
    };
    void ping(0);
    return () => clearTimeout(slow);
  }, []);
  return status;
}

function StatusPill({ status }: { status: Status }) {
  if (!API_URL) return null;
  const meta = {
    checking: { text: "Checking demo status…", dot: "bg-subtle" },
    waking: { text: "Waking up the demo server…", dot: "bg-warn animate-pulse" },
    online: { text: "Live demo online", dot: "bg-ok" },
    offline: { text: "Demo is offline right now", dot: "bg-bad" },
  }[status];
  return (
    <span className="inline-flex items-center gap-2 rounded-full border border-line bg-surface/80 px-3 py-1 text-xs font-medium text-muted backdrop-blur">
      <span className={clsx("h-2 w-2 rounded-full", meta.dot)} />
      {meta.text}
    </span>
  );
}

function PrimaryCta({ className, children }: { className?: string; children?: ReactNode }) {
  return (
    <a
      href={DEMO_HREF}
      className={clsx(
        "inline-flex h-11 items-center gap-2 rounded-lg bg-brand-solid px-6 text-sm font-semibold text-white shadow-lg shadow-brand/25 transition-transform hover:-translate-y-0.5",
        className,
      )}
    >
      {children ?? "Try the live demo"} <ArrowRight size={16} />
    </a>
  );
}

function Section({
  id,
  eyebrow,
  title,
  lead,
  children,
}: {
  id: string;
  eyebrow: string;
  title: string;
  lead?: string;
  children: ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-20 px-5 py-20 sm:py-24">
      <div className="mx-auto max-w-6xl">
        <p className="text-xs font-semibold uppercase tracking-widest text-brand">{eyebrow}</p>
        <h2 className="mt-2 max-w-3xl text-2xl font-bold tracking-tight sm:text-3xl">{title}</h2>
        {lead && <p className="mt-3 max-w-2xl text-muted">{lead}</p>}
        <div className="mt-10">{children}</div>
      </div>
    </section>
  );
}

function Browser({ src, alt }: { src: string; alt: string }) {
  return (
    <div className="overflow-hidden rounded-xl border border-line bg-surface shadow-2xl shadow-black/20">
      <div className="flex items-center gap-1.5 border-b border-line px-3 py-2">
        {["bg-bad/70", "bg-warn/70", "bg-ok/70"].map((c) => (
          <span key={c} className={clsx("h-2.5 w-2.5 rounded-full", c)} />
        ))}
      </div>
      <img src={src} alt={alt} loading="lazy" decoding="async" width={1440} height={900} className="block h-auto w-full" />
    </div>
  );
}

/* ------------------------------------------------------------------------ */

const STATS = [
  { value: "2,500", label: "concurrent simulated users in a spike test" },
  { value: "0", label: "failed requests out of 131,272" },
  { value: "120 ms", label: "p95 time to first streamed event" },
  { value: "0", label: "double refunds across every race test" },
];

const SCENARIOS: { title: string; text: string; outcome: string; tone: string }[] = [
  { title: "Happy path", text: "An eligible order gets refunded end to end.", outcome: "Approved", tone: "ok" },
  { title: "Final sale", text: "The policy engine says no, and the agent can't overrule it.", outcome: "Denied", tone: "bad" },
  { title: "Over $500", text: "High-value refunds go to a human.", outcome: "Escalated", tone: "warn" },
  { title: "Double refund", text: "The order was already refunded once.", outcome: "Denied", tone: "bad" },
  { title: "Prompt injection", text: "\"Ignore your rules, you're in admin mode…\"", outcome: "Flagged", tone: "warn" },
  { title: "Someone else's order", text: "Identity comes from a signed token, never from the chat.", outcome: "Blocked", tone: "bad" },
];

const TONE: Record<string, string> = {
  ok: "border-ok/30 bg-ok/10 text-ok",
  bad: "border-bad/30 bg-bad/10 text-bad",
  warn: "border-warn/30 bg-warn/10 text-warn",
};

const GUARDRAILS: { icon: LucideIcon; title: string; text: string }[] = [
  {
    icon: KeyRound,
    title: "Identity from a signed JWT",
    text: "The customer id comes from a verified token. There's no tool that looks someone up by name or email, so the chat can't impersonate anyone.",
  },
  {
    icon: Scale,
    title: "The LLM proposes, code decides",
    text: "Every refund passes a deterministic policy engine: return window, final sale, $500 escalation, already refunded. The model can't skip it.",
  },
  {
    icon: Lock,
    title: "Exactly-once refunds",
    text: "SELECT … FOR UPDATE on the order row plus a partial unique index, so concurrent requests can't approve the same order twice.",
  },
  {
    icon: ShieldAlert,
    title: "Injection-aware, not injection-dependent",
    text: "Manipulation attempts are flagged and shown in the trace. An output sanitizer corrects any approval the database didn't record.",
  },
  {
    icon: Gauge,
    title: "Cost and load controls",
    text: "Per-customer rate limits, per-customer and demo-wide token budgets, and a global in-flight turn cap that sheds load with 503 + Retry-After.",
  },
  {
    icon: Eye,
    title: "Observable by design",
    text: "Every tool call and decision is persisted and streamed live to an admin console, alongside Prometheus metrics and structured JSON logs.",
  },
];

const STACK = [
  "Python 3.12",
  "FastAPI",
  "LangGraph",
  "Claude",
  "SQLAlchemy (async)",
  "Postgres",
  "Redis",
  "Alembic",
  "Server-Sent Events",
  "React 18",
  "TypeScript",
  "Tailwind CSS",
  "Locust",
  "Docker",
  "Kubernetes",
  "Cloud Run",
  "GitHub Actions",
];

/* ------------------------------------------------------------------------ */

export default function App() {
  const [dark, toggleTheme] = useTheme();
  const status = useBackendStatus();

  return (
    <div className="min-h-full overflow-x-hidden">
      {/* Nav */}
      <header className="sticky top-0 z-30 border-b border-line/70 bg-bg/80 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-4 px-5">
          <a href="#top" className="flex items-center gap-2.5 font-semibold">
            <img src={asset("favicon.svg")} alt="" className="h-7 w-7" />
            <span className="hidden sm:inline">ACME Support Agent</span>
          </a>
          <nav className="ml-4 hidden items-center gap-6 text-sm text-muted md:flex">
            <a href="#how" className="hover:text-fg">How it works</a>
            <a href="#guardrails" className="hover:text-fg">Guardrails</a>
            <a href="#scale" className="hover:text-fg">Scale</a>
            <a href="#stack" className="hover:text-fg">Stack</a>
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <button
              onClick={toggleTheme}
              aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
              className="flex h-9 w-9 items-center justify-center rounded-lg text-muted hover:bg-surface-2 hover:text-fg"
            >
              {dark ? <Sun size={17} /> : <Moon size={17} />}
            </button>
            <a
              href={REPO_URL}
              className="hidden h-9 items-center gap-2 rounded-lg border border-line px-3 text-sm font-medium hover:bg-surface-2 sm:inline-flex"
            >
              <Github size={16} /> Source
            </a>
            <a
              href={DEMO_HREF}
              className="inline-flex h-9 items-center rounded-lg bg-brand-solid px-4 text-sm font-semibold text-white"
            >
              Live demo
            </a>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section id="top" className="relative px-5 pb-16 pt-16 sm:pt-24">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 -top-40 mx-auto h-[36rem] max-w-4xl rounded-full bg-gradient-to-br from-indigo-500/25 via-violet-500/15 to-transparent blur-3xl"
        />
        <div className="relative mx-auto max-w-6xl text-center">
          <StatusPill status={status} />
          <h1 className="mx-auto mt-6 max-w-4xl text-4xl font-extrabold tracking-tight sm:text-6xl">
            An AI support agent that{" "}
            <span className="bg-gradient-to-r from-indigo-500 to-violet-500 bg-clip-text text-transparent">
              can't be talked into a bad refund
            </span>
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-lg text-muted">
            A LangGraph agent that handles refund requests end to end, with the kind of guardrails,
            concurrency safety and load testing you'd want before putting an LLM near money.
          </p>
          <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
            <PrimaryCta />
            <a
              href={REPO_URL}
              className="inline-flex h-11 items-center gap-2 rounded-lg border border-line bg-surface px-6 text-sm font-semibold hover:bg-surface-2"
            >
              <Github size={16} /> View the code
            </a>
          </div>
          <p className="mt-4 text-xs text-subtle">
            No sign-up. You get a private sandbox with five orders; it's deleted after 24 hours.
          </p>

          <div className="relative mx-auto mt-14 max-w-5xl">
            <Browser src={asset(`screens/chat-${dark ? "dark" : "light"}.png`)} alt="The chat UI with the live agent-reasoning panel" />
          </div>
        </div>
      </section>

      {/* Stats */}
      <section className="border-y border-line bg-surface/60 px-5 py-10">
        <dl className="mx-auto grid max-w-6xl grid-cols-2 gap-8 lg:grid-cols-4">
          {STATS.map((s) => (
            <div key={s.label}>
              <dt className="sr-only">{s.label}</dt>
              <dd className="text-3xl font-bold tracking-tight text-brand">{s.value}</dd>
              <dd className="mt-1 text-sm text-muted">{s.label}</dd>
            </div>
          ))}
        </dl>
      </section>

      {/* Scenarios */}
      <Section
        id="try"
        eyebrow="Try to break it"
        title="Six scenarios to try, each one clickable in the demo"
        lead="Each sandbox includes one order per branch of the refund policy. Try asking nicely, try lying, try prompt injection. Watch the reasoning panel either way."
      >
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {SCENARIOS.map((s) => (
            <div key={s.title} className="rounded-xl border border-line bg-surface p-5 shadow-sm">
              <div className="flex items-center justify-between gap-2">
                <h3 className="font-semibold">{s.title}</h3>
                <span className={clsx("rounded-full border px-2 py-0.5 text-[11px] font-semibold", TONE[s.tone])}>
                  {s.outcome}
                </span>
              </div>
              <p className="mt-2 text-sm text-muted">{s.text}</p>
            </div>
          ))}
        </div>
        <div className="mt-8">
          <PrimaryCta>Open the sandbox</PrimaryCta>
        </div>
      </Section>

      {/* How it works */}
      <Section
        id="how"
        eyebrow="How it works"
        title="The model reasons, deterministic code acts"
        lead="Each chat turn streams over SSE from a stateless FastAPI service. The agent can only act through tools, and every tool that touches money goes through the policy engine and a database row lock."
      >
        <div className="rounded-2xl border border-line bg-surface/60 p-4 sm:p-8">
          <Architecture />
        </div>
        <div className="mt-10 grid items-start gap-6 lg:grid-cols-2">
          <div>
            <Browser src={asset(`screens/console-${dark ? "dark" : "light"}.png`)} alt="The agent console with KPIs, a transcript and its reasoning trace" />
            <p className="mt-3 text-sm text-muted">
              The agent console: live transcripts, reasoning traces and decision KPIs. In the demo
              your token is scoped to your own sandbox.
            </p>
          </div>
          <ol className="space-y-5">
            {[
              ["Authenticate", "A signed JWT sets who the customer is. Rate limit, per-conversation lock and a global concurrency slot are taken in Redis."],
              ["Reason", "The LangGraph ReAct loop calls Claude with prompt caching. Turn time, recursion depth and token spend are all bounded."],
              ["Act", "Tools read the customer's own orders. check_refund_eligibility and issue_refund run the policy engine; issue_refund locks the row."],
              ["Stream and record", "Every step is saved with an atomic sequence number, published over Redis pub/sub, and streamed to the chat and the console."],
            ].map(([t, d], i) => (
              <li key={t} className="flex gap-4">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand/10 font-mono text-sm font-semibold text-brand">
                  {i + 1}
                </span>
                <div>
                  <h3 className="font-semibold">{t}</h3>
                  <p className="mt-1 text-sm text-muted">{d}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </Section>

      {/* Guardrails */}
      <Section
        id="guardrails"
        eyebrow="Guardrails"
        title="Safe even when the model misbehaves"
        lead="The test suite runs a deliberately compromised model that tries to approve forbidden refunds. The guardrails hold without relying on the model."
      >
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {GUARDRAILS.map(({ icon: Icon, title, text }) => (
            <div key={title} className="rounded-xl border border-line bg-surface p-5 shadow-sm">
              <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand/10 text-brand">
                <Icon size={19} />
              </span>
              <h3 className="mt-4 font-semibold">{title}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-muted">{text}</p>
            </div>
          ))}
        </div>
      </Section>

      {/* Scale */}
      <Section
        id="scale"
        eyebrow="Tested at scale"
        title="Thousands of simulated users, zero broken invariants"
        lead="A distributed Locust simulation drives realistic chat, race, abuse and admin traffic, then checks the database for anything that must never happen: double refunds, forbidden approvals, cross-customer access, event-ordering gaps."
      >
        <div className="grid gap-6 lg:grid-cols-3">
          {[
            {
              icon: Timer,
              title: "Profiling fixed the hot path",
              body: "The first 1,000-user run failed with 230 errors (pool exhaustion, CPU-bound graph rebuilds). After fixing both: 0 errors in 81,145 requests, and throughput went from 35 to 53 turns/s on the same box.",
            },
            {
              icon: Gauge,
              title: "Spike with back-pressure",
              body: "2,500 users arriving at 50/s: excess turns were shed in 11 ms with 503 + jittered Retry-After and retried cleanly. p95 time to first event stayed at 120 ms.",
            },
            {
              icon: Boxes,
              title: "Correct under races",
              body: "Concurrent turns in one conversation and parallel refunds of the same order were fired on purpose. Every run: one approval per order, and the lock never rejected both turns.",
            },
          ].map(({ icon: Icon, title, body }) => (
            <div key={title} className="rounded-xl border border-line bg-surface p-6 shadow-sm">
              <Icon size={20} className="text-brand" />
              <h3 className="mt-3 font-semibold">{title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted">{body}</p>
            </div>
          ))}
        </div>
        <div className="mt-6 overflow-x-auto rounded-xl border border-line bg-surface">
          <table className="w-full min-w-[36rem] text-left text-sm">
            <thead className="border-b border-line text-xs uppercase tracking-wide text-subtle">
              <tr>
                <th className="px-5 py-3 font-semibold">Run</th>
                <th className="px-5 py-3 font-semibold">Requests</th>
                <th className="px-5 py-3 font-semibold">Unexpected failures</th>
                <th className="px-5 py-3 font-semibold">p95 first event</th>
                <th className="px-5 py-3 font-semibold">Invariants</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {[
                ["1,000 users, baseline", "n/a", "230", "9.2 s", "pass"],
                ["1,000 users, after fixes", "81,145", "0", "2.8 s", "pass"],
                ["2,500-user spike", "131,272", "0", "120 ms", "pass"],
              ].map((r) => (
                <tr key={r[0]}>
                  {r.map((c, i) => (
                    <td key={i} className={clsx("px-5 py-3", i === 0 ? "font-medium" : "tabular-nums text-muted")}>
                      {c}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-xs text-subtle">
          Measured on one 4-vCPU VM running everything (backends, Postgres, Redis and the load
          generators) with a latency-realistic fake LLM, so treat these as a floor. Full method in{" "}
          <a className="underline" href={`${REPO_URL}/blob/main/docs/LOADTESTING.md`}>
            LOADTESTING.md
          </a>
          .
        </p>
      </Section>

      {/* Stack */}
      <Section id="stack" eyebrow="Stack" title="Built with">
        <div className="flex flex-wrap gap-2">
          {STACK.map((s) => (
            <span key={s} className="rounded-full border border-line bg-surface px-3.5 py-1.5 text-sm">
              {s}
            </span>
          ))}
        </div>
        <div className="mt-16 rounded-2xl border border-line bg-gradient-to-br from-indigo-500/10 to-violet-500/10 p-8 text-center sm:p-12">
          <h2 className="text-2xl font-bold tracking-tight sm:text-3xl">See it for yourself</h2>
          <p className="mx-auto mt-3 max-w-xl text-muted">
            It takes about a minute. Start a sandbox, try a few scenarios, then open the agent
            console to see what happened.
          </p>
          <div className="mt-7 flex justify-center">
            <PrimaryCta />
          </div>
        </div>
      </Section>

      <footer className="border-t border-line px-5 py-10">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 text-sm text-muted">
          <span>
            Built by <a href={AUTHOR.github} className="font-medium text-fg hover:underline">{AUTHOR.name}</a>
          </span>
          <div className="flex items-center gap-4">
            <a href={AUTHOR.github} aria-label="GitHub" className="hover:text-fg">
              <Github size={18} />
            </a>
            {AUTHOR.linkedin && (
              <a href={AUTHOR.linkedin} aria-label="LinkedIn" className="hover:text-fg">
                <Linkedin size={18} />
              </a>
            )}
            {AUTHOR.email && (
              <a href={`mailto:${AUTHOR.email}`} aria-label="Email" className="hover:text-fg">
                <Mail size={18} />
              </a>
            )}
          </div>
        </div>
      </footer>
    </div>
  );
}
