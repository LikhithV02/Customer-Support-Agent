import type { StepEvent } from "../types";

const STEP_META: Record<
  string,
  { label: string; dot: string; chip: string }
> = {
  model: { label: "Reasoning", dot: "bg-slate-400", chip: "text-slate-300" },
  tool_call: { label: "Tool call", dot: "bg-sky-400", chip: "text-sky-300" },
  tool_result: { label: "Tool result", dot: "bg-slate-500", chip: "text-slate-300" },
  policy_eval: { label: "Policy check", dot: "bg-amber-400", chip: "text-amber-300" },
  decision: { label: "Decision", dot: "bg-emerald-400", chip: "text-emerald-300" },
  injection_flag: {
    label: "Injection attempt",
    dot: "bg-rose-500",
    chip: "text-rose-300",
  },
  error: { label: "Error", dot: "bg-rose-500", chip: "text-rose-300" },
};

const DECISION_COLOR: Record<string, string> = {
  approved: "text-emerald-300 border-emerald-500/40 bg-emerald-500/10",
  denied: "text-rose-300 border-rose-500/40 bg-rose-500/10",
  escalated: "text-amber-300 border-amber-500/40 bg-amber-500/10",
};

function Json({ value }: { value: unknown }) {
  return (
    <pre className="mt-1 overflow-x-auto rounded bg-slate-950/70 p-2 font-mono text-[11px] leading-relaxed text-slate-300">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

function StepBody({ step }: { step: StepEvent }) {
  const p = step.payload || {};
  switch (step.step_type) {
    case "model":
      return <p className="text-sm text-slate-300">{p.text}</p>;
    case "tool_call":
      return (
        <div>
          <span className="font-mono text-xs text-sky-300">{p.tool}(…)</span>
          {p.args && Object.keys(p.args).length > 0 && <Json value={p.args} />}
        </div>
      );
    case "policy_eval": {
      const r = p.result || {};
      return (
        <div>
          <span className="font-mono text-xs text-slate-400">{p.tool}</span>
          <DecisionBadge decision={r.decision} />
          {Array.isArray(r.reasons) && (
            <ul className="mt-1 list-disc pl-4 text-xs text-slate-400">
              {r.reasons.map((reason: string, i: number) => (
                <li key={i}>{reason}</li>
              ))}
            </ul>
          )}
        </div>
      );
    }
    case "decision": {
      const r = p.result || {};
      return (
        <div>
          <span className="font-mono text-xs text-slate-400">{p.tool}</span>
          <DecisionBadge decision={r.decision} />
          {Array.isArray(r.reasons) && (
            <ul className="mt-1 list-disc pl-4 text-xs text-slate-400">
              {r.reasons.map((reason: string, i: number) => (
                <li key={i}>{reason}</li>
              ))}
            </ul>
          )}
        </div>
      );
    }
    case "injection_flag":
      return (
        <div className="text-xs text-rose-300">
          Flagged patterns:{" "}
          <span className="font-mono">{(p.patterns || []).join(", ")}</span>
          <Json value={{ text: p.text }} />
        </div>
      );
    case "error":
      return <p className="text-sm text-rose-300">{p.message}</p>;
    default:
      return <Json value={p.result ?? p} />;
  }
}

function DecisionBadge({ decision }: { decision?: string }) {
  if (!decision) return null;
  const cls = DECISION_COLOR[decision] || "text-slate-300 border-slate-600 bg-slate-800";
  return (
    <span
      className={`ml-2 rounded-full border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${cls}`}
    >
      {decision}
    </span>
  );
}

export default function ReasoningTimeline({ steps }: { steps: StepEvent[] }) {
  if (steps.length === 0) {
    return (
      <p className="px-1 py-6 text-center text-sm text-slate-500">
        No reasoning steps yet.
      </p>
    );
  }
  return (
    <ol className="space-y-3">
      {steps.map((step) => {
        const meta = STEP_META[step.step_type] || STEP_META.tool_result;
        return (
          <li key={`${step.id}-${step.seq}`} className="flex gap-3">
            <div className="mt-1.5 flex flex-col items-center">
              <span className={`h-2.5 w-2.5 rounded-full ${meta.dot}`} />
              <span className="mt-1 w-px flex-1 bg-slate-800" />
            </div>
            <div className="flex-1 rounded-lg border border-slate-800 bg-slate-900/50 p-3">
              <div className="flex items-center justify-between">
                <span className={`text-xs font-semibold uppercase tracking-wide ${meta.chip}`}>
                  {meta.label}
                </span>
                <span className="text-[11px] text-slate-600">#{step.seq}</span>
              </div>
              <div className="mt-1.5">
                <StepBody step={step} />
              </div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
