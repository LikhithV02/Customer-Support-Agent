import clsx from "clsx";
import { Bot, CheckCircle2, Database, Scale, Swords } from "lucide-react";
import summary from "../../backend/redteam/summary.json";

/**
 * The latest reviewed promptfoo red-team run (backend/redteam/summary.json,
 * written by `python -m redteam.report`).
 */

type Bucket = {
  id: string;
  label: string;
  attacks: number;
  defended: number;
  judged_unsafe: number;
  errored: number;
};
type Finding = { id: string; title: string; detail: string; fix: string; status: string; found_in?: string };
type Summary = {
  generated_at: string;
  model: string;
  attacks: number;
  agent_turns: number;
  defended: number;
  judged_unsafe: number;
  errored: number;
  ground_truth: Record<string, number>;
  injection_flagged_turns: number;
  sanitizer_corrections: number;
  by_plugin: Bucket[];
  by_strategy: Bucket[];
  review: { reviewed_at: string | null; flagged: Record<string, number>; findings: Finding[] };
};
const S = summary as Summary;

const GROUND_TRUTH: Record<string, string> = {
  forbidden_approval: "Refunds approved against policy",
  forbidden_escalation: "Escalations the policy didn't allow",
  double_refund: "Orders refunded twice",
  cross_customer_leak: "Other customers' data leaked",
  unbacked_approval_claim: "Approvals claimed but not recorded",
};

const VERDICTS: { key: string; label: string; cls: string }[] = [
  { key: "fixed", label: "real, now fixed", cls: "bg-bad/80" },
  { key: "false_positive", label: "grader false positive", cls: "bg-subtle/60" },
  { key: "acceptable", label: "acceptable on review", cls: "bg-info/70" },
  { key: "harness", label: "test-harness limit", cls: "bg-muted/40" },
  { key: "unreviewed", label: "not yet reviewed", cls: "bg-warn/80" },
];

const date = new Date(S.generated_at).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });

export default function RedTeam() {
  const max = Math.max(...S.by_plugin.map((p) => p.attacks));
  const violations = Object.values(S.ground_truth).reduce((a, b) => a + b, 0);
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-3">
        {[
          [Bot, "Attacker model", "GPT-5.6 writes attacks from a description of the app, and adapts multi-turn attacks to each reply."],
          [Swords, "Real agent, real tools", "Each attack gets a fresh sandbox customer: ten orders on the policy boundaries plus someone else's order to steal."],
          [Database, "Judged twice", "A grader model reads every conversation, and the database is checked after every turn for money that moved."],
        ].map(([Icon, t, d], i) => {
          const I = Icon as typeof Bot;
          return (
            <div key={i} className="rounded-xl border border-line bg-surface p-5 shadow-sm">
              <I size={19} className="text-brand" />
              <h3 className="mt-3 font-semibold">{t as string}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-muted">{d as string}</p>
            </div>
          );
        })}
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        <div className="rounded-xl border border-line bg-surface p-6 shadow-sm lg:col-span-2">
          <div className="flex items-baseline justify-between gap-3">
            <h3 className="font-semibold">Database ground truth</h3>
            <span className="text-xs text-subtle">{date}</span>
          </div>
          <p className="mt-1 text-sm text-muted">
            {S.attacks.toLocaleString()} attacks, {S.agent_turns.toLocaleString()} agent turns
            {S.errored ? `, ${S.errored} lost to network errors` : ""}.
          </p>
          <ul className="mt-5 space-y-3">
            {Object.entries(GROUND_TRUTH).map(([k, label]) => (
              <li key={k} className="flex items-center justify-between gap-3 text-sm">
                <span className="text-muted">{label}</span>
                <span
                  className={clsx(
                    "rounded-full border px-2.5 py-0.5 font-mono text-xs font-semibold tabular-nums",
                    S.ground_truth[k] ? "border-bad/30 bg-bad/10 text-bad" : "border-ok/30 bg-ok/10 text-ok",
                  )}
                >
                  {S.ground_truth[k]}
                </span>
              </li>
            ))}
          </ul>
          <div className="mt-6 grid grid-cols-2 gap-3 border-t border-line pt-5 text-sm">
            <div>
              <div className="font-mono text-2xl font-bold tabular-nums text-brand">{S.injection_flagged_turns}</div>
              <div className="text-xs text-muted">turns flagged as injection</div>
            </div>
            <div>
              <div className="font-mono text-2xl font-bold tabular-nums text-brand">{S.sanitizer_corrections}</div>
              <div className="text-xs text-muted">replies the output sanitizer annotated (see below)</div>
            </div>
          </div>
          {violations === 0 && (
            <p className="mt-5 flex gap-2 rounded-lg bg-ok/10 p-3 text-xs leading-relaxed text-ok">
              <Scale size={15} className="shrink-0" />
              No attack moved money or exposed another customer, because the policy gate and
              the ownership check are code, not prompt.
            </p>
          )}
        </div>

        <div className="rounded-xl border border-line bg-surface p-6 shadow-sm lg:col-span-3">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h3 className="font-semibold">Attacks by type</h3>
            <span className="inline-flex items-center gap-4 text-xs text-muted">
              <span className="inline-flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-sm bg-ok/70" /> defended
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-sm bg-warn/80" /> grader flagged
              </span>
            </span>
          </div>
          <ul className="mt-5 space-y-2.5">
            {S.by_plugin.map((p) => (
              <li key={p.id} className="grid grid-cols-[minmax(0,11rem)_1fr_3rem] items-center gap-3 text-sm">
                <span className="truncate text-muted" title={p.label}>
                  {p.label}
                </span>
                <span className="flex h-4 overflow-hidden rounded bg-surface-2" style={{ width: `${(p.attacks / max) * 100}%` }}>
                  <span className="bg-ok/70" style={{ width: `${(p.defended / p.attacks) * 100}%` }} />
                  <span className="bg-warn/80" style={{ width: `${(p.judged_unsafe / p.attacks) * 100}%` }} />
                </span>
                <span className="text-right font-mono text-xs tabular-nums text-subtle">{p.attacks}</span>
              </li>
            ))}
          </ul>
          <div className="mt-6 border-t border-line pt-5">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-subtle">
              {S.judged_unsafe} flagged by the grader, each read by a person
            </h4>
            <div className="mt-3 flex h-3 overflow-hidden rounded-full bg-surface-2" aria-hidden>
              {VERDICTS.map((v) =>
                S.review.flagged[v.key] ? (
                  <span key={v.key} className={v.cls} style={{ width: `${(S.review.flagged[v.key] / S.judged_unsafe) * 100}%` }} />
                ) : null,
              )}
            </div>
            <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1.5 text-xs text-muted">
              {VERDICTS.filter((v) => S.review.flagged[v.key]).map((v) => (
                <li key={v.key} className="inline-flex items-center gap-1.5">
                  <span className={clsx("h-2.5 w-2.5 rounded-sm", v.cls)} />
                  <span className="font-mono tabular-nums text-fg">{S.review.flagged[v.key]}</span> {v.label}
                </li>
              ))}
            </ul>
          </div>
          <div className="mt-6 border-t border-line pt-5">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-subtle">Delivered as</h4>
            <div className="mt-3 flex flex-wrap gap-2">
              {S.by_strategy.map((s) => (
                <span key={s.id} className="rounded-full border border-line bg-surface-2 px-3 py-1 text-xs">
                  {s.label} <span className="font-mono text-subtle">{s.attacks}</span>
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>

      {S.review.findings.length > 0 && (
        <div className="grid gap-4 md:grid-cols-2">
          {S.review.findings.map((f) => (
            <div key={f.id} className="rounded-xl border border-line bg-surface p-5 shadow-sm">
              <div className="flex items-start justify-between gap-3">
                <h3 className="font-semibold">{f.title}</h3>
                <span className="inline-flex shrink-0 items-center gap-1 rounded-full border border-ok/30 bg-ok/10 px-2 py-0.5 text-[11px] font-semibold text-ok">
                  <CheckCircle2 size={12} /> {f.status}
                </span>
              </div>
              {f.found_in && <p className="mt-1 text-xs text-subtle">Found in the {f.found_in}</p>}
              <p className="mt-2 text-sm leading-relaxed text-muted">{f.detail}</p>
              <p className="mt-2 text-sm leading-relaxed">
                <span className="font-medium">Fix: </span>
                <span className="text-muted">{f.fix}</span>
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
