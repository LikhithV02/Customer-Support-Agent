import clsx from "clsx";
import { useState } from "react";
import baseline from "../../backend/evals/baseline.json";
import { Code, Panel } from "./ui";

/**
 * The eval-harness results, read straight from the baseline CI gates against
 * (backend/evals/baseline.json), so the page can't drift from what's enforced.
 */

type Entry = { model: string; rates: Record<string, number>; tone: number | null; cases: Record<string, boolean> };
const ENTRIES = Object.values(baseline as Record<string, Entry>);

const MODEL_LABEL: Record<string, string> = {
  "scripted-fake": "Scripted",
  "gemini-3.8-flash": "Gemini 3.8 Flash",
  "gpt-5.6-sol-medium": "GPT‑5.6",
};
const COLUMNS = Object.keys(MODEL_LABEL)
  .map((m) => ENTRIES.find((e) => e.model === m))
  .filter((e): e is Entry => !!e);
const LIVE = COLUMNS.filter((e) => e.tone !== null);

const METRICS: { key: string; label: string; text: string; gate: string; floor?: boolean }[] = [
  { key: "ledger_safe", label: "Money safe", text: "no approval the policy forbids", gate: "every case", floor: true },
  { key: "no_unbacked_approval", label: "No false approvals", text: "never claims what the tool didn't record", gate: "every case", floor: true },
  { key: "decision_matches_policy", label: "Right decision", text: "each order ends in its policy outcome", gate: "≤ 2 pt drop" },
  { key: "tool_correctness", label: "Right tools", text: "eligibility checked before any decision", gate: "≤ 2 pt drop" },
];

// Case files in backend/evals/cases/, keyed by id prefix.
const GROUPS = [
  { prefix: "edge-", label: "Policy edge cases", cls: "bg-brand" },
  { prefix: "inj-", label: "Prompt injection & social engineering", cls: "bg-warn" },
  { prefix: "mt-", label: "Multi‑turn pressure", cls: "bg-info" },
];

const pct = (v: number) => `${Math.round(v * 100)}%`;

function Scoreboard() {
  return (
    <Panel className="min-w-0 flex-[1_1_34rem] overflow-hidden">
      <div className="flex flex-wrap justify-between gap-3 border-b border-line-soft px-5 py-4">
        <span className="font-semibold">Scoreboard · committed baselines</span>
        <span className="font-mono text-xs text-subtle">evals/baseline.json</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[35rem] border-collapse text-sm">
          <thead>
            <tr className="text-left font-mono text-[11px] uppercase tracking-[0.06em] text-subtle">
              <th className="px-5 py-3 font-medium">Score</th>
              <th className="px-2.5 py-3 font-medium">Gate</th>
              {COLUMNS.map((c) => (
                <th key={c.model} className="px-2.5 py-3 text-right font-medium last:pr-5">
                  {MODEL_LABEL[c.model]}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="font-mono">
            {METRICS.map((m) => (
              <tr key={m.key} className="border-t border-line-soft">
                <td className="px-5 py-3.5 font-sans">
                  <div className="font-semibold">{m.label}</div>
                  <div className="text-xs text-subtle">{m.text}</div>
                </td>
                <td className="whitespace-nowrap px-2.5 py-3.5 text-xs text-muted">{m.gate}</td>
                {COLUMNS.map((c) => (
                  <td key={c.model} className={clsx("px-2.5 py-3.5 text-right last:pr-5", m.floor && "text-brand")}>
                    {pct(c.rates[m.key] ?? 0)}
                  </td>
                ))}
              </tr>
            ))}
            <tr className="border-t border-line-soft">
              <td className="px-5 py-3.5 font-sans">
                <div className="font-semibold">Tone</div>
                <div className="text-xs text-subtle">LLM judge (Opik G‑Eval), 0–1</div>
              </td>
              <td className="whitespace-nowrap px-2.5 py-3.5 text-xs text-muted">≤ 0.03 drop</td>
              {COLUMNS.map((c) => (
                <td key={c.model} className={clsx("px-2.5 py-3.5 text-right last:pr-5", c.tone === null && "text-subtle")}>
                  {c.tone === null ? "n/a" : c.tone.toFixed(2)}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function CaseMatrix() {
  const [model, setModel] = useState(LIVE[0]?.model ?? "");
  const entry = LIVE.find((e) => e.model === model) ?? LIVE[0];
  const ids = Object.keys(entry?.cases ?? {});
  const [hovered, setHovered] = useState(ids[0] ?? "");
  const passed = ids.filter((id) => entry.cases[id]).length;

  return (
    <Panel className="flex min-w-0 flex-[1_1_24rem] flex-col gap-5 p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="font-semibold">Every case, latest live run</span>
        <div className="flex gap-1.5" role="group" aria-label="Model">
          {LIVE.map((e) => (
            <button
              key={e.model}
              onClick={() => setModel(e.model)}
              aria-pressed={e.model === model}
              className={clsx(
                "min-h-9 rounded-lg border px-2.5 font-mono text-xs",
                e.model === model ? "border-brand bg-brand text-on-brand" : "border-line text-muted hover:text-fg",
              )}
            >
              {MODEL_LABEL[e.model]}
            </button>
          ))}
        </div>
      </div>
      {GROUPS.map((g) => {
        const group = ids.filter((id) => id.startsWith(g.prefix));
        return (
          <div key={g.prefix}>
            <div className="flex justify-between font-mono text-xs text-muted">
              <span>{g.label}</span>
              <span>{group.length}</span>
            </div>
            <div
              role="img"
              aria-label={`${group.filter((id) => entry.cases[id]).length} of ${group.length} ${g.label.toLowerCase()} passed`}
              className="mt-2 flex flex-wrap gap-[5px]"
            >
              {group.map((id) => (
                <span
                  key={id}
                  title={id}
                  onMouseEnter={() => setHovered(id)}
                  className={clsx(
                    "h-[18px] w-[18px] rounded",
                    entry.cases[id] ? g.cls : "border-2 border-bad bg-transparent",
                    id === hovered && "ring-2 ring-fg ring-offset-1 ring-offset-panel",
                  )}
                />
              ))}
            </div>
          </div>
        );
      })}
      <div className="mt-auto flex flex-wrap justify-between gap-3 rounded-[10px] border border-line-soft bg-surface px-3.5 py-3 font-mono text-[12.5px]">
        <span>{hovered}</span>
        <span className={entry?.cases[hovered] ? "text-ok" : "text-bad"}>
          {entry?.cases[hovered] ? "PASS" : "FAIL"} · {passed}/{ids.length} overall
        </span>
      </div>
    </Panel>
  );
}

export function EvalResults() {
  return (
    <>
      <div className="flex flex-wrap items-stretch gap-6">
        <Scoreboard />
        <CaseMatrix />
      </div>
      <div className="mt-6 grid gap-4 sm:grid-cols-3">
        {[
          ["fork PRs", "Scripted mode", "A deterministic fake model. Free, no keys, same gates."],
          ["every PR", "Live mode", "The real provider plus a tone judge. A failed deterministic check retries once on fresh orders."],
          ["traceable", "Opik experiment per PR", <>Every run is logged as <Code>pr-&lt;n&gt;-&lt;sha&gt;</Code> for side‑by‑side diffs.</>],
        ].map(([k, t, d]) => (
          <div key={String(t)} className="rounded-2xl border border-line-soft p-5">
            <div className="font-mono text-xs text-subtle">{k}</div>
            <div className="mt-2 font-semibold">{t}</div>
            <div className="mt-1 text-sm text-muted">{d}</div>
          </div>
        ))}
      </div>
    </>
  );
}
