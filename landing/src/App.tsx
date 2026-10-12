import clsx from "clsx";
import { useEffect, useState, type ReactNode } from "react";
import Architecture from "./Architecture";
import Deployment from "./Deployment";
import { EvalResults } from "./Evaluation";
import RedTeam from "./RedTeam";
import Simulation from "./Simulation";
import Trace from "./Trace";
import { ArrowRight, Code, Figure, Section } from "./ui";
import redteamSummary from "../../backend/redteam/summary.json";
import { API_URL, APP_URL, AUTHOR, REPO_URL } from "./config";

const DEMO_HREF = APP_URL || REPO_URL;
const asset = (p: string) => `${import.meta.env.BASE_URL}${p}`;
const breaches = Object.values(redteamSummary.ground_truth).reduce((a, b) => a + b, 0);

/* ------------------------------------------------------------------------ */

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
  const meta = {
    checking: { text: "Checking the live demo…", dot: "bg-subtle" },
    waking: { text: "Waking up the demo server…", dot: "bg-warn animate-pulse" },
    online: { text: "Live demo online · Cloud Run · Gemini 3.8 Flash", dot: "bg-ok shadow-[0_0_0_4px_rgb(var(--c-ok)/0.15)]" },
    offline: { text: "Open source · runs locally with Docker", dot: "bg-subtle" },
  }[status];
  return (
    <span className="inline-flex items-center gap-2.5 rounded-full border border-line px-3 py-1.5 font-mono text-xs text-muted">
      <span className={clsx("h-2 w-2 rounded-full", meta.dot)} />
      {meta.text}
    </span>
  );
}

function PrimaryCta({ children, big }: { children: ReactNode; big?: boolean }) {
  return (
    <a
      href={DEMO_HREF}
      className={clsx(
        "inline-flex items-center gap-2.5 rounded-xl bg-brand font-semibold text-on-brand transition-transform hover:-translate-y-0.5",
        big ? "min-h-[52px] px-6" : "min-h-11 px-4 text-sm",
      )}
    >
      {children} <ArrowRight />
    </a>
  );
}

function GhostCta({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a href={href} className="inline-flex min-h-[52px] items-center gap-2.5 rounded-xl border border-line px-5 font-medium hover:border-subtle">
      {children}
    </a>
  );
}

function Mark({ size = 26 }: { size?: number }) {
  return (
    <svg aria-hidden width={size} height={size} viewBox="0 0 26 26" fill="none">
      <rect x="1" y="1" width="24" height="24" rx="6" stroke="rgb(var(--c-brand))" strokeWidth="1.5" />
      <path d="M7 13.5l4 4 8-9" stroke="rgb(var(--c-brand))" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function GithubIcon() {
  return (
    <svg aria-hidden width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 19c-4.3 1.4-4.3-2.5-6-3m12 5v-3.5c0-1 .1-1.4-.5-2 2.8-.3 5.5-1.4 5.5-6a4.6 4.6 0 0 0-1.3-3.2 4.2 4.2 0 0 0-.1-3.2s-1.1-.3-3.5 1.3a12.3 12.3 0 0 0-6.2 0C6.5 2.8 5.4 3.1 5.4 3.1a4.2 4.2 0 0 0-.1 3.2A4.6 4.6 0 0 0 4 9.5c0 4.6 2.7 5.7 5.5 6-.6.6-.6 1.2-.5 2V21" />
    </svg>
  );
}

/* ------------------------------------------------------------------------ */

const STATS: { value: ReactNode; label: string; accent?: boolean }[] = [
  { value: "83", label: "golden conversations graded on every pull request" },
  { value: "100%", label: "money‑safe and policy‑correct on Gemini 3.8 Flash and GPT‑5.6", accent: true },
  { value: `${breaches} / ${redteamSummary.attacks}`, label: "AI‑written attacks that moved money or leaked data" },
  { value: "131,272", label: "requests in a 2,500‑user spike, 0 failed" },
  { value: <>120<span className="text-2xl text-muted"> ms</span></>, label: "p95 time to first streamed event under that spike" },
];

const POLICY: [string, "DENY" | "ESCALATE" | "APPROVE"][] = [
  ["Not delivered yet?", "DENY"],
  ["Final‑sale item?", "DENY"],
  ["Already refunded once?", "DENY"],
  ["More than 30 days since delivery?", "DENY"],
  ["Over $500?", "ESCALATE"],
  ["Everything else", "APPROVE"],
];
const VERDICT_CLS = { DENY: "bg-bad/10 text-bad", ESCALATE: "bg-warn/10 text-warn", APPROVE: "bg-ok/10 text-ok" };

const LAYERS: [string, string, ReactNode][] = [
  ["L1 · EDGE", "Load and cost controls", "Per‑customer rate limits and daily token budgets in Redis, a global in‑flight turn cap that sheds with a jittered 503 + Retry‑After."],
  ["L2 · IDENTITY", "Who you are comes from a token", "Customer id from a verified JWT. No tool looks anyone up by name or email, so “I'm Carol” changes nothing. Foreign conversations return 404."],
  ["L3 · PROMPT", "Injection‑aware, not injection‑dependent", <>System rules separated from untrusted data. Fuzzy detection for <Code>ignroe</Code>, <Code>i.g.n.o.r.e</Code>, zero‑width and Base64 tricks, flagged in the trace.</>],
  ["L4 · TOOL GATE", "The tool re‑checks the policy", <><Code>issue_refund</Code> records “approved” only if the engine allows it; otherwise “denied” or “escalated”. This is the real enforcement.</>],
  ["L5 · LEDGER", "Exactly‑once refunds", "Row lock plus a partial unique index. Concurrent race probes under load: 100% single approval."],
  ["L6 · OUTPUT", "No unbacked promises", <>A sanitizer corrects any “approved” or “processed” claim that no successful <Code>issue_refund</Code> backed in that turn.</>],
];

const STACK = [
  "Python 3.12", "FastAPI", "LangGraph", "Gemini · GPT‑5.6 · Claude", "Opik", "promptfoo", "SQLAlchemy async",
  "Postgres", "Redis", "Alembic", "SSE", "React 18 · TypeScript", "Tailwind", "Locust", "Docker", "Kubernetes",
  "Cloud Run", "GitHub Actions",
];

/* ------------------------------------------------------------------------ */

function ZoneCard({ tone, title, children }: { tone: "warn" | "brand"; title: string; children: ReactNode }) {
  return (
    <div className={clsx("rounded-xl border p-4", tone === "warn" ? "border-warn/20 bg-warn/[0.03]" : "border-brand/20 bg-brand/[0.03]")}>
      <div className="font-semibold">{title}</div>
      <div className="mt-1 text-[13px] text-muted">{children}</div>
    </div>
  );
}

function TrustZones() {
  return (
    <div className="mt-6 flex flex-wrap overflow-hidden rounded-[18px] border border-line bg-panel">
      <div className="flex min-w-0 flex-[1_1_15rem] flex-col gap-3.5 border-line-soft p-6 sm:border-r">
        <div className="font-mono text-[11px] uppercase tracking-[0.1em] text-subtle">Client → API</div>
        <div className="rounded-xl border border-line bg-surface p-4">
          <div className="font-semibold">Chat + agent console</div>
          <div className="mt-1 text-[13px] text-muted">React SPA on Cloudflare. Signed JWT from the host site; live reasoning over SSE.</div>
        </div>
        <div className="rounded-xl border border-line bg-surface p-4">
          <div className="font-semibold">FastAPI, stateless</div>
          <div className="mt-2 flex flex-wrap gap-1.5 font-mono text-[11.5px] text-muted">
            {["JWT → 401", "rate limit → 429", "turn lock → 409", "slot → 503 + Retry‑After"].map((c) => (
              <span key={c} className="rounded-md bg-surface-2 px-2 py-0.5">{c}</span>
            ))}
          </div>
        </div>
      </div>
      <div className="flex min-w-0 flex-[1_1_18rem] flex-col gap-3.5 bg-[#0F1114] p-6">
        <div className="flex justify-between gap-3 font-mono text-[11px] uppercase tracking-[0.1em]">
          <span className="text-warn">Probabilistic zone</span>
          <span className="text-subtle">can be wrong · can be lied to</span>
        </div>
        <ZoneCard tone="warn" title="LangGraph ReAct loop">Agent ⇄ tools until a final reply. Bounded recursion, max_tokens, per‑turn and per‑customer token budgets.</ZoneCard>
        <ZoneCard tone="warn" title="LLM provider, swappable">Gemini · GPT‑5.6 · Claude · any OpenAI‑compatible proxy, with circuit‑breaker failover.</ZoneCard>
        <ZoneCard tone="warn" title="Six tools, nothing else">
          <span className="font-mono text-xs leading-relaxed">get_my_profile · get_order · list_orders · check_refund_eligibility · <span className="text-fg">issue_refund</span> · <span className="text-fg">escalate_to_human</span></span>
        </ZoneCard>
      </div>
      <div aria-hidden className="w-0.5 shrink-0 bg-[repeating-linear-gradient(to_bottom,rgb(var(--c-brand))_0_8px,transparent_8px_16px)] max-sm:h-0.5 max-sm:w-full max-sm:bg-[repeating-linear-gradient(to_right,rgb(var(--c-brand))_0_8px,transparent_8px_16px)]" />
      <div className="flex min-w-0 flex-[1_1_18rem] flex-col gap-3.5 p-6">
        <div className="flex justify-between gap-3 font-mono text-[11px] uppercase tracking-[0.1em]">
          <span className="text-brand">Deterministic zone</span>
          <span className="text-subtle">the only way money moves</span>
        </div>
        <ZoneCard tone="brand" title="policy/engine.py">Pure function of the order and today's date. Runs in <Code>check_refund_eligibility</Code> and again inside <Code>issue_refund</Code>.</ZoneCard>
        <ZoneCard tone="brand" title="Postgres refund ledger"><Code>SELECT … FOR UPDATE</Code> plus a partial unique index: one approved refund per order, even under races.</ZoneCard>
        <ZoneCard tone="brand" title="Reasoning events">Every thought, tool call and decision persisted with an atomic sequence number and published to Redis.</ZoneCard>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------------ */

export default function App() {
  const status = useBackendStatus();
  return (
    <div className="min-h-full overflow-x-hidden">
      {/* Nav */}
      <header className="sticky top-0 z-30 border-b border-line-soft bg-bg/85 backdrop-blur-md">
        <div className="mx-auto flex min-h-16 max-w-page flex-wrap items-center gap-x-7 gap-y-2 px-6 py-2">
          <a href="#top" className="flex items-center gap-2.5 font-mono text-sm font-semibold">
            <Mark />
            <span>refund-agent</span>
            <span className="hidden font-normal text-subtle sm:inline">/ case study</span>
          </a>
          <nav aria-label="Sections" className="hidden gap-6 text-sm text-muted lg:flex">
            {[["#system", "System design"], ["#evals", "Evals"], ["#redteam", "Red team"], ["#simulation", "Simulation"], ["#ship", "Infra"]].map(([h, l]) => (
              <a key={h} href={h} className="hover:text-fg">{l}</a>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-2.5">
            <a href={REPO_URL} className="hidden min-h-11 items-center gap-2 rounded-[10px] border border-line px-3.5 text-sm font-medium hover:border-subtle sm:inline-flex">
              <GithubIcon /> Source
            </a>
            <PrimaryCta>Live demo</PrimaryCta>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section id="top" className="mx-auto flex max-w-page flex-wrap items-start gap-14 px-6 pb-14 pt-16 sm:pt-20">
        <div className="min-w-0 flex-[1_1_28rem] pt-2">
          <StatusPill status={status} />
          <h1 className="mt-7 text-[clamp(2.6rem,4.7vw,4.25rem)] font-semibold leading-[1] tracking-[-0.045em]">
            An AI agent that handles refunds, and <span className="text-brand">can't be talked into a bad one.</span>
          </h1>
          <p className="mt-7 max-w-xl text-lg text-muted">
            A LangGraph support agent that approves, denies or escalates e‑commerce refunds. The model reasons;
            deterministic code decides. It's graded on 83 conversations on every PR, attacked by another LLM every week,
            and load‑tested to 2,500 concurrent users.
          </p>
          <div className="mt-9 flex flex-wrap gap-3">
            <PrimaryCta big>Try to break it</PrimaryCta>
            <GhostCta href={REPO_URL}>Read the code</GhostCta>
          </div>
          <p className="mt-4 text-[13px] text-subtle">
            No sign‑up. You get a private sandbox with one order per refund‑policy branch, deleted after 24 hours.
          </p>
          <div className="mt-11 flex items-center gap-3.5 border-t border-line-soft pt-6">
            <div className="flex h-10 w-10 items-center justify-center rounded-full border border-line bg-surface-2 font-mono text-[13px] text-brand">
              {AUTHOR.name.split(" ").map((w) => w[0]).join("").slice(0, 2)}
            </div>
            <div className="text-sm leading-snug">
              <div className="font-semibold">Designed and built end‑to‑end by {AUTHOR.name}</div>
              <div className="text-subtle">Agent · backend · evals · red team · load testing · infra</div>
            </div>
          </div>
        </div>
        <div className="min-w-0 flex-[1_1_30rem]">
          <Trace />
        </div>
      </section>

      {/* Proof strip */}
      <section aria-label="Results at a glance" className="border-y border-line-soft bg-[#0D0F12]">
        <dl className="mx-auto grid max-w-page grid-cols-[repeat(auto-fit,minmax(12.5rem,1fr))] px-6">
          {STATS.map((s, i) => (
            <div key={s.label} className={clsx("flex flex-col-reverse py-8 pr-6", i > 0 && "sm:pl-6", i < STATS.length - 1 && "sm:border-r sm:border-line-soft")}>
              <dt className="mt-2.5 text-sm text-muted">{s.label}</dt>
              <dd className={clsx("m-0 text-[44px] font-semibold leading-none tracking-[-0.04em]", s.accent && "text-brand")}>{s.value}</dd>
            </div>
          ))}
        </dl>
      </section>

      {/* Product */}
      <section aria-label="The product" className="mx-auto grid max-w-page gap-6 px-6 pt-20 md:grid-cols-2">
        {[
          ["chat", "/chat", "the customer view, with the agent's reasoning streaming alongside.", "Customer chat with the agent's live reasoning panel"],
          ["console", "/console", "every tool call, policy check and decision, live from any backend pod.", "Agent console with decision KPIs, a transcript and its reasoning trace"],
        ].map(([f, path, text, alt]) => (
          <figure key={f} className="m-0">
            <div className="overflow-hidden rounded-[14px] border border-line bg-surface">
              <img src={asset(`screens/${f}-dark.png`)} alt={alt} loading="lazy" decoding="async" width={1440} height={900} className="block h-auto w-full" />
            </div>
            <figcaption className="mt-3 text-sm text-muted">
              <Code>{path}</Code> — {text}
            </figcaption>
          </figure>
        ))}
      </section>

      {/* 01 System design */}
      <Section
        id="system"
        n="01"
        eyebrow="System design"
        title={<>The LLM proposes.<br />The code disposes.</>}
        lead={<>Refund approval is never decided by the model's text. To move money the agent must call <Code>issue_refund</Code>, and that tool re‑runs the deterministic policy engine and locks the order row before it writes anything. A jailbroken model can call the tool. The tool still says no.</>}
      >
        <Figure caption="Request path">
          <Architecture />
        </Figure>
        <TrustZones />
        <div className="mt-8 flex flex-wrap gap-8">
          <div className="min-w-0 flex-[1_1_20rem]">
            <h3 className="text-[22px] font-semibold tracking-[-0.02em]">Policy as code, evaluated in order</h3>
            <p className="mt-2.5 max-w-md text-[15px] text-muted">
              The same rules are given to the model in plain English and enforced in Python. Eval expectations come from
              the order's policy branch, so a test case can't encode the wrong answer.
            </p>
            <p className="mt-4 max-w-md text-[15px] text-muted">
              Ownership sits above all of it: a customer only ever sees their own orders, and someone else's order looks
              exactly like one that doesn't exist.
            </p>
          </div>
          <ol className="m-0 min-w-0 flex-[1_1_30rem] overflow-hidden rounded-2xl border border-line p-0">
            {POLICY.map(([rule, verdict], i) => (
              <li key={rule} className={clsx("flex items-center gap-4 px-5 py-3.5", i < POLICY.length - 1 ? "border-b border-line-soft" : "bg-brand/[0.035]")}>
                <span className="w-5 font-mono text-xs text-subtle">{i < POLICY.length - 1 ? i + 1 : "✓"}</span>
                <span className="flex-1">{rule}</span>
                <span className={clsx("rounded-md px-2.5 py-1 font-mono text-xs font-semibold", VERDICT_CLS[verdict])}>{verdict}</span>
              </li>
            ))}
          </ol>
        </div>
      </Section>

      {/* 02 Defense in depth */}
      <Section
        id="guardrails"
        n="02"
        eyebrow="Defense in depth"
        title="Six layers. Each one assumes the one above it failed."
        lead="The test suite drives a deliberately compromised model that tries to approve forbidden refunds. The layers hold without trusting the model."
      >
        <div className="grid overflow-hidden rounded-2xl border border-line sm:grid-cols-2 lg:grid-cols-3">
          {LAYERS.map(([tag, title, text]) => (
            <div key={tag} className="border-b border-r border-line-soft p-6 sm:-mb-px sm:-mr-px">
              <div className="font-mono text-xs text-brand">{tag}</div>
              <div className="mt-2.5 text-[17px] font-semibold">{title}</div>
              <p className="mt-2 text-sm text-muted">{text}</p>
            </div>
          ))}
        </div>
      </Section>

      {/* 03 Evaluation */}
      <Section
        id="evals"
        n="03"
        eyebrow="Evaluation"
        title="A prompt change that makes it worse fails the build."
        lead={<>83 conversations run through the same code path as <Code>/api/chat</Code> on every PR. The checks read the refund ledger and tool results, not just the reply, then compare against a committed baseline.</>}
      >
        <EvalResults />
      </Section>

      {/* 04 Red team */}
      <Section
        id="redteam"
        n="04"
        eyebrow="Red team"
        title="Then another AI tried to break it."
        lead="The golden set only holds attacks someone thought to write. So an attacker model (promptfoo with GPT‑5.6) writes new ones, including multi‑turn Crescendo attacks that adapt to each reply. A grader judges every answer, and the database is checked after every turn. It runs weekly in GitHub Actions."
      >
        <RedTeam />
      </Section>

      {/* 05 Simulation */}
      <Section
        id="simulation"
        n="05"
        eyebrow="Load simulation"
        title="Then 2,500 simulated customers showed up at once."
        lead="A distributed Locust simulation drives chat, race, abuse and admin traffic against 10,000 synthetic customers, then checks the database for ten things that must never happen. Everything ran on one 4‑vCPU VM, so these numbers are a floor."
      >
        <Simulation />
        <p className="mt-4 text-xs text-subtle">
          Fake LLM at 1.5 s median per call with 0.5% injected errors, so the test measures this system rather than a
          provider. Full method in{" "}
          <a className="underline hover:text-fg" href={`${REPO_URL}/blob/main/docs/LOADTESTING.md`}>LOADTESTING.md</a>.
        </p>
      </Section>

      {/* 06 Infra */}
      <Section id="ship" n="06" eyebrow="Infrastructure" title="Shipped, not just prototyped.">
        <Figure caption="Where it runs">
          <Deployment />
        </Figure>
        <div className="mt-6 grid gap-4 md:grid-cols-3">
          {[
            ["Kubernetes‑ready", "Kustomize base + dev/prod overlays: HPA (3–30), PodDisruptionBudgets, NetworkPolicy, retention CronJob, in‑cluster Locust."],
            ["CI that blocks regressions", "Lint, tests on SQLite and real Postgres + Redis, manifest checks, a 50‑user load smoke and the golden‑set evals on every PR. Red team weekly."],
            ["Observable", "Prometheus metrics, structured JSON logs with request ids, Opik traces of every agent turn."],
          ].map(([t, d]) => (
            <div key={t} className="rounded-2xl border border-line-soft p-6">
              <div className="font-semibold">{t}</div>
              <p className="mt-2 text-sm text-muted">{d}</p>
            </div>
          ))}
        </div>
        <ul className="mt-10 flex flex-wrap gap-2 font-mono text-[12.5px]" aria-label="Tech stack">
          {STACK.map((s) => (
            <li key={s} className="rounded-full border border-line px-3 py-1.5 text-soft">{s}</li>
          ))}
        </ul>
      </Section>

      {/* CTA */}
      <section className="mx-auto max-w-page px-6 pt-32">
        <div className="flex flex-wrap items-end justify-between gap-8 rounded-[22px] border border-brand/25 bg-brand/[0.035] p-[clamp(2rem,6vw,4.5rem)]">
          <div className="min-w-0 flex-[1_1_32rem]">
            <div className="font-mono text-xs uppercase tracking-[0.12em] text-brand">Your turn</div>
            <h2 className="mt-4 text-[clamp(2.1rem,5vw,4rem)] font-semibold leading-none tracking-[-0.045em]">
              Try to get a refund you shouldn't.
            </h2>
            <p className="mt-4 max-w-lg text-[17px] text-muted">
              Lie, plead, inject, switch accounts. Watch the reasoning console decide, and see the ledger not move.
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <PrimaryCta big>Open the sandbox</PrimaryCta>
            <GhostCta href={REPO_URL}>GitHub</GhostCta>
          </div>
        </div>
      </section>

      <footer className="mx-auto flex max-w-page flex-wrap items-center justify-between gap-6 px-6 pb-12 pt-16 text-sm text-muted">
        <div>
          <span className="font-semibold text-fg">{AUTHOR.name}</span> · AI / backend engineer
        </div>
        <nav aria-label="Contact" className="flex flex-wrap gap-5 font-mono text-[13px]">
          <a href={AUTHOR.github} className="hover:text-fg">github</a>
          {AUTHOR.linkedin && <a href={AUTHOR.linkedin} className="hover:text-fg">linkedin</a>}
          {AUTHOR.email && <a href={`mailto:${AUTHOR.email}`} className="hover:text-fg">email</a>}
          <a href={`${REPO_URL}/blob/main/docs/VERIFICATION.md`} className="hover:text-fg">verification log</a>
        </nav>
      </footer>
    </div>
  );
}
