import summary from "../../backend/redteam/summary.json";
import { Code, Panel } from "./ui";

/**
 * The latest reviewed promptfoo red-team run (backend/redteam/summary.json,
 * written by `python -m redteam.report`).
 */

type Bucket = { id: string; label: string; attacks: number; defended: number; judged_unsafe: number; errored: number };
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
  by_plugin: Bucket[];
  by_strategy: Bucket[];
  review: { reviewed_at: string | null; flagged: Record<string, number>; findings: Finding[] };
};
const S = summary as Summary;

const GROUND_TRUTH: Record<string, string> = {
  forbidden_approval: "forbidden approvals",
  forbidden_escalation: "forbidden escalations",
  double_refund: "double refunds",
  cross_customer_leak: "cross‑customer leaks",
  unbacked_approval_claim: "unbacked approval claims",
};

const REVIEW_LABEL: Record<string, string> = {
  false_positive: "false positives",
  harness: "harness issues",
  acceptable: "acceptable on review",
  fixed: "real bug, now fixed",
};

const share = (n: number, of: number) => `${(n / of) * 100}%`;

export default function RedTeam() {
  const breaches = Object.values(S.ground_truth).reduce((a, b) => a + b, 0);
  const review = Object.entries(S.review.flagged)
    .filter(([, n]) => n > 0)
    .map(([k, n]) => `${n} ${REVIEW_LABEL[k] ?? k}`)
    .join(", ");

  return (
    <>
      <div className="flex flex-wrap items-stretch gap-6">
        {/* Ground truth */}
        <div className="flex min-w-0 flex-[1_1_21rem] flex-col rounded-2xl border border-brand/25 bg-brand/[0.035] p-6 sm:p-7">
          <div className="font-mono text-xs uppercase tracking-[0.08em] text-brand">Ground truth · database after every turn</div>
          <div className="mt-5 flex flex-wrap items-baseline gap-3">
            <span className="text-[88px] font-semibold leading-[0.9] tracking-[-0.06em] text-brand">{breaches}</span>
            <span className="text-muted">
              breaches in {S.attacks} attacks · {S.agent_turns} agent turns
            </span>
          </div>
          <ul className="mt-6 font-mono text-[13px]">
            {Object.entries(S.ground_truth).map(([k, n]) => (
              <li key={k} className="flex justify-between border-t border-brand/15 py-2.5">
                <span className="text-soft">{GROUND_TRUTH[k] ?? k}</span>
                <span>{n}</span>
              </li>
            ))}
          </ul>
          <p className="mt-auto pt-5 text-[13px] text-muted">
            The grader flagged {S.judged_unsafe} replies. On review: {review}. {S.injection_flagged_turns} turns were
            flagged as injection.
          </p>
        </div>

        {/* By plugin */}
        <Panel className="min-w-0 flex-[2_1_32rem] px-6 py-5">
          <div className="flex flex-wrap justify-between gap-4">
            <span className="font-semibold">Defended, by attack goal</span>
            <span className="flex flex-wrap gap-3.5 font-mono text-[11.5px] text-muted">
              {[
                ["bg-brand", "defended"],
                ["bg-warn", "judged unsafe"],
                ["bg-[#4A4E57]", "errored"],
              ].map(([c, l]) => (
                <span key={l} className="inline-flex items-center gap-1.5">
                  <span className={`h-2.5 w-2.5 rounded-sm ${c}`} />
                  {l}
                </span>
              ))}
            </span>
          </div>
          <ul className="mt-5 space-y-2.5">
            {S.by_plugin.map((p) => (
              <li key={p.id} className="flex items-center gap-3.5 text-[13.5px]">
                <span className="w-32 shrink-0 truncate text-soft sm:w-48" title={p.label}>
                  {p.label}
                </span>
                <span
                  className="flex h-2.5 flex-1 overflow-hidden rounded-[3px] bg-surface-2"
                  role="img"
                  aria-label={`${p.defended} of ${p.attacks} defended`}
                >
                  <span className="bg-brand" style={{ width: share(p.defended, p.attacks) }} />
                  <span className="bg-warn" style={{ width: share(p.judged_unsafe, p.attacks) }} />
                  <span className="bg-[#4A4E57]" style={{ width: share(p.errored, p.attacks) }} />
                </span>
                <span className="w-12 shrink-0 text-right font-mono text-[12.5px] text-muted">
                  {p.defended}/{p.attacks}
                </span>
              </li>
            ))}
          </ul>
        </Panel>
      </div>

      {/* Strategies */}
      <div className="mt-6 grid grid-cols-[repeat(auto-fit,minmax(10.5rem,1fr))] gap-3">
        {S.by_strategy.map((s) => (
          <div key={s.id} className="rounded-xl border border-line-soft px-4 py-4">
            <div className="font-mono text-[22px] font-medium">
              {s.defended}
              <span className="text-subtle">/{s.attacks}</span>
            </div>
            <div className="mt-1 text-[13px] text-muted">{s.label}</div>
          </div>
        ))}
      </div>

      {/* Findings */}
      <h3 className="mt-14 text-[22px] font-semibold tracking-[-0.02em]">What it found, and what changed</h3>
      <div className="mt-5 grid grid-cols-[repeat(auto-fit,minmax(18rem,1fr))] gap-4">
        {S.review.findings.map((f) => (
          <article key={f.id} className="flex flex-col gap-2.5 rounded-2xl border border-line p-5">
            <div className="flex justify-between gap-2.5 font-mono text-[11.5px]">
              <span className="text-subtle">{f.found_in}</span>
              <span className={f.status === "fixed" ? "text-ok" : "text-warn"}>{f.status.toUpperCase()}</span>
            </div>
            <div className="font-semibold">{f.title}</div>
            <p className="m-0 text-sm text-muted">{f.fix}</p>
          </article>
        ))}
      </div>
      <p className="mt-4 text-xs text-subtle">
        Attacker and grader: {S.model}. Raw results in <Code>backend/redteam/summary.json</Code>.
      </p>
    </>
  );
}
