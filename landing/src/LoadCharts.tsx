import clsx from "clsx";

/** Load-test charts. Every number comes from docs/LOADTESTING.md ("Results"). */

const MIX = [
  { label: "Customers", share: 85, cls: "bg-brand", text: "2–3 turn refund chats on all five policy branches, then reload the conversation" },
  { label: "Racers", share: 10, cls: "bg-info", text: "two turns at once in one chat, two refunds of one order at once" },
  { label: "Attackers", share: 3, cls: "bg-bad", text: "injection, other customers' chats, no or wrong token, oversize messages, bursts" },
  { label: "Support leads", share: 2, cls: "bg-ok", text: "admin console with a live event stream held open" },
];

const RUNS = ["1,000 users, baseline", "1,000 users, after fixes", "2,500-user spike"];
const RUN_CLS = ["bg-bad/70", "bg-brand/70", "bg-ok/80"];

const CHARTS: { title: string; values: number[]; better: "lower" | "higher"; fmt: (v: number) => string }[] = [
  { title: "p95 time to first streamed event", values: [9.2, 2.8, 0.12], better: "lower", fmt: (v) => (v < 1 ? `${Math.round(v * 1000)} ms` : `${v} s`) },
  { title: "p95 full turn (incl. simulated LLM)", values: [26, 12, 5.6], better: "lower", fmt: (v) => `${v} s` },
  { title: "Unexpected failures", values: [230, 0, 0], better: "lower", fmt: (v) => v.toLocaleString() },
];

export default function LoadCharts() {
  return (
    <div className="grid gap-6 lg:grid-cols-5">
      <div className="rounded-xl border border-line bg-surface p-6 shadow-sm lg:col-span-2">
        <h3 className="font-semibold">Who the simulated users are</h3>
        <p className="mt-1 text-sm text-muted">
          Locust users with real JWTs, each checking its own answers while it runs.
        </p>
        <div className="mt-5 flex h-3 overflow-hidden rounded-full bg-surface-2" aria-hidden>
          {MIX.map((m) => (
            <span key={m.label} className={m.cls} style={{ width: `${m.share}%` }} />
          ))}
        </div>
        <ul className="mt-5 space-y-3.5">
          {MIX.map((m) => (
            <li key={m.label} className="flex gap-3">
              <span className={clsx("mt-1.5 h-2.5 w-2.5 shrink-0 rounded-sm", m.cls)} />
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="text-sm font-medium">{m.label}</span>
                  <span className="font-mono text-sm tabular-nums text-muted">{m.share}%</span>
                </div>
                <p className="text-xs leading-relaxed text-subtle">{m.text}</p>
              </div>
            </li>
          ))}
        </ul>
      </div>

      <div className="rounded-xl border border-line bg-surface p-6 shadow-sm lg:col-span-3">
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
          {RUNS.map((r, i) => (
            <span key={r} className="inline-flex items-center gap-2 text-xs text-muted">
              <span className={clsx("h-2.5 w-2.5 rounded-sm", RUN_CLS[i])} />
              {r}
            </span>
          ))}
        </div>
        <div className="mt-6 space-y-7">
          {CHARTS.map((c) => {
            const max = Math.max(...c.values);
            return (
              <figure key={c.title}>
                <figcaption className="flex items-baseline justify-between text-sm">
                  <span className="font-medium">{c.title}</span>
                  <span className="text-xs text-subtle">{c.better} is better</span>
                </figcaption>
                <div className="mt-2.5 space-y-1.5">
                  {c.values.map((v, i) => (
                    <div key={i} className="flex items-center gap-3">
                      <div className="h-5 flex-1 rounded bg-surface-2">
                        <div
                          className={clsx("h-full rounded", RUN_CLS[i])}
                          style={{ width: v === 0 ? "0%" : `max(${(v / max) * 100}%, 4px)` }}
                          role="presentation"
                        />
                      </div>
                      <span className="w-16 text-right font-mono text-xs tabular-nums text-muted">
                        <span className="sr-only">{RUNS[i]}: </span>
                        {c.fmt(v)}
                      </span>
                    </div>
                  ))}
                </div>
              </figure>
            );
          })}
        </div>
      </div>
    </div>
  );
}
