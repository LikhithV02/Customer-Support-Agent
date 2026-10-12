import clsx from "clsx";
import { Panel } from "./ui";

/** Load-test results. Every number comes from docs/LOADTESTING.md ("Results"). */

const RUNS = [
  {
    name: "RUN 1 · 1,000 users",
    verdict: "FAILED",
    verdictCls: "text-bad",
    cardCls: "bg-bad/[0.03]",
    big: "230",
    unit: "failures",
    lines: ["35 turns/s", "p95 first event 9.2 s", "46 × HTTP 500 · 63 torn streams"],
    good: "policy gate held: 0 violations",
  },
  {
    name: "RUN 2 · after profiling",
    verdict: "LATENCY SLO MISSED",
    verdictCls: "text-warn",
    cardCls: "",
    big: "0",
    unit: "of 81,145 failed",
    lines: ["53 turns/s (+51%)", "p95 first event 2.8 s", "saturates at ~700–800 users"],
    good: "836 approved · 0 violations",
  },
  {
    name: "RUN 3 · 2,500-user spike",
    verdict: "PASSED",
    verdictCls: "text-brand",
    cardCls: "bg-brand/[0.035]",
    big: "0",
    unit: "of 131,272 failed",
    lines: ["p50 / p95 / p99 first event 30 / 120 / 260 ms", "34,566 shed with 503 in 11 ms", "race + guardrail probes 100% correct"],
    good: "10 / 10 invariants passed",
  },
];

// p95 time to first streamed event, seconds; SLO is 1.5 s.
const P95 = [
  { run: "run 1", v: 9.2, cls: "bg-bad" },
  { run: "run 2", v: 2.8, cls: "bg-warn" },
  { run: "run 3", v: 0.12, cls: "bg-brand" },
];
const SLO = 1.5;
const fmt = (v: number) => (v < 1 ? `${Math.round(v * 1000)} ms` : `${v} s`);

const MIX = [
  { label: "Customers", share: 85, cls: "bg-brand" },
  { label: "Racers", share: 10, cls: "bg-info" },
  { label: "Attackers", share: 3, cls: "bg-bad" },
  { label: "Support leads", share: 2, cls: "bg-ok" },
];

const FIXES = [
  ["py‑spy showed ~50% of CPU rebuilding tools and recompiling the graph every turn.", "Built once per process; identity now flows through RunnableConfig."],
  ["DB pool exhaustion caused the 500s.", "Reasoning events now write with two Core statements instead of the ORM unit of work."],
  ["Errors after SSE headers tore streams.", "Every stream now ends with a clean error event, and locks are still released."],
  ["Shed clients caused a retry storm.", "Jittered Retry‑After plus client back‑off cut shed traffic from 279 to 96 req/s."],
];

export default function Simulation() {
  const max = P95[0].v;
  return (
    <>
      <div className="grid overflow-hidden rounded-2xl border border-line md:grid-cols-3">
        {RUNS.map((r, i) => (
          <div key={r.name} className={clsx("p-6", r.cardCls, i > 0 && "border-t border-line-soft md:border-l md:border-t-0")}>
            <div className="flex justify-between gap-2 font-mono text-xs">
              <span className="text-muted">{r.name}</span>
              <span className={r.verdictCls}>{r.verdict}</span>
            </div>
            <div className="mt-4 text-[40px] font-semibold leading-none tracking-[-0.04em]">
              {r.big} <span className="text-base font-normal tracking-normal text-muted">{r.unit}</span>
            </div>
            <ul className="mt-4 space-y-1.5 font-mono text-[12.5px] text-soft">
              {r.lines.map((l) => (
                <li key={l}>{l}</li>
              ))}
              <li className="text-ok">{r.good}</li>
            </ul>
          </div>
        ))}
      </div>

      <div className="mt-6 flex flex-wrap items-stretch gap-6">
        <Panel className="min-w-0 flex-[1_1_28rem] p-6">
          <div className="flex flex-wrap justify-between gap-3">
            <span className="font-semibold">p95 time to first streamed event</span>
            <span className="font-mono text-xs text-subtle">SLO {SLO} s</span>
          </div>
          <div
            role="img"
            aria-label={`p95 time to first event: ${P95.map((p) => `${p.run} ${fmt(p.v)}`).join(", ")}; the SLO is ${SLO} seconds`}
            className="relative mt-7 space-y-5"
          >
            <div
              aria-hidden
              className="absolute -bottom-2.5 -top-2.5 border-l-[1.5px] border-dashed border-fg/50"
              style={{ left: `calc(4rem + (100% - 4rem) * ${SLO / max})` }}
            />
            {P95.map((p) => (
              <div key={p.run} className="flex items-center">
                <span className="w-16 shrink-0 font-mono text-xs text-muted">{p.run}</span>
                <span className="flex flex-1 items-center gap-2.5">
                  <span className={clsx("h-[26px] min-w-1 rounded", p.cls)} style={{ width: `${(p.v / max) * 100}%` }} />
                  {p.v < max && <span className="font-mono text-[12.5px]">{fmt(p.v)}</span>}
                </span>
              </div>
            ))}
          </div>
          <div className="mt-5 flex justify-between pl-16 font-mono text-[11.5px] text-subtle">
            <span>0</span>
            <span>run 1 = {fmt(max)}</span>
          </div>

          <div className="mt-8 border-t border-line-soft pt-5">
            <div className="text-sm font-semibold">Who the simulated users are</div>
            <div className="mt-3 flex h-2.5 overflow-hidden rounded-full" aria-hidden>
              {MIX.map((m) => (
                <span key={m.label} className={m.cls} style={{ width: `${m.share}%` }} />
              ))}
            </div>
            <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1.5 font-mono text-xs text-muted">
              {MIX.map((m) => (
                <li key={m.label} className="flex items-center gap-1.5">
                  <span className={clsx("h-2 w-2 rounded-sm", m.cls)} />
                  {m.label} {m.share}%
                </li>
              ))}
            </ul>
          </div>
        </Panel>

        <Panel className="min-w-0 flex-[1_1_26rem] p-6">
          <div className="font-semibold">What profiling under load fixed</div>
          <ol className="mt-5 space-y-4 text-sm">
            {FIXES.map(([problem, fix], i) => (
              <li key={problem} className="flex gap-3.5">
                <span className="font-mono text-brand">{String(i + 1).padStart(2, "0")}</span>
                <span>
                  {problem} <span className="text-muted">{fix}</span>
                </span>
              </li>
            ))}
          </ol>
          <div className="mt-6 rounded-[10px] bg-surface px-4 py-3.5 text-[13.5px] text-muted">
            <span className="font-semibold text-fg">Capacity:</span> ~15–17 turns/s per vCPU, about 250 concurrent chatting
            users per vCPU. The HPA scales from 3 to 30 pods.
          </div>
        </Panel>
      </div>
    </>
  );
}
