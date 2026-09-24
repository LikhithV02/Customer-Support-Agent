import clsx from "clsx";
import {
  AlertTriangle,
  Brain,
  CircleDollarSign,
  Gauge,
  Info,
  ShieldAlert,
  ShieldCheck,
  Wrench,
  type LucideIcon,
} from "lucide-react";
import type { Outcome, StepEvent } from "../types";
import { OUTCOME_META, type Tone } from "../lib/outcome";
import { Badge } from "./ui";

const STEP_META: Record<string, { label: string; icon: LucideIcon; tone: Tone }> = {
  model: { label: "Reasoning", icon: Brain, tone: "neutral" },
  tool_call: { label: "Tool call", icon: Wrench, tone: "info" },
  tool_result: { label: "Tool result", icon: Wrench, tone: "neutral" },
  policy_eval: { label: "Policy check", icon: ShieldCheck, tone: "warn" },
  decision: { label: "Decision", icon: CircleDollarSign, tone: "ok" },
  injection_flag: { label: "Injection attempt", icon: ShieldAlert, tone: "bad" },
  error: { label: "Error", icon: AlertTriangle, tone: "bad" },
  usage: { label: "Tokens", icon: Gauge, tone: "neutral" },
  budget_exhausted: { label: "Budget exhausted", icon: Gauge, tone: "warn" },
  output_correction: { label: "Output corrected", icon: ShieldAlert, tone: "bad" },
  notice: { label: "Notice", icon: Info, tone: "info" },
};

const DOT: Record<Tone, string> = {
  ok: "bg-ok/15 text-ok",
  bad: "bg-bad/15 text-bad",
  warn: "bg-warn/15 text-warn",
  info: "bg-info/15 text-info",
  brand: "bg-brand/15 text-brand",
  neutral: "bg-surface-2 text-muted",
};

function Json({ value, label = "Details" }: { value: unknown; label?: string }) {
  return (
    <details className="group mt-1.5">
      <summary className="cursor-pointer select-none text-[11px] font-medium text-subtle hover:text-muted">
        {label}
      </summary>
      <pre className="mt-1 max-h-56 overflow-auto rounded-md bg-surface-2 p-2 font-mono text-[11px] leading-relaxed text-muted">
        {JSON.stringify(value, null, 2)}
      </pre>
    </details>
  );
}

export function DecisionBadge({ decision }: { decision?: string }) {
  if (!decision) return null;
  const meta = OUTCOME_META[decision as Outcome];
  return <Badge tone={meta?.tone ?? "neutral"}>{decision.toUpperCase()}</Badge>;
}

function argsSummary(args: Record<string, unknown> | undefined): string {
  if (!args) return "";
  return Object.entries(args)
    .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
    .join(", ");
}

function StepBody({ step }: { step: StepEvent }) {
  const p = step.payload || {};
  switch (step.step_type) {
    case "model":
      return <p className="text-[13px] leading-relaxed text-fg/90">{p.text}</p>;
    case "tool_call":
      return (
        <code className="break-all font-mono text-xs leading-5 text-info">
          {p.tool}({argsSummary(p.args)})
        </code>
      );
    case "policy_eval":
    case "decision": {
      const r = p.result || {};
      return (
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <code className="font-mono text-xs text-muted">{p.tool}</code>
            <DecisionBadge decision={r.decision} />
            {typeof r.amount === "number" && (
              <span className="text-xs text-muted">${r.amount.toFixed(2)}</span>
            )}
          </div>
          {Array.isArray(r.reasons) && r.reasons.length > 0 && (
            <ul className="mt-1.5 list-disc space-y-0.5 pl-4 text-xs text-muted">
              {r.reasons.map((reason: string, i: number) => (
                <li key={i}>{reason}</li>
              ))}
            </ul>
          )}
        </div>
      );
    }
    case "tool_result": {
      const r = p.result || {};
      return (
        <div>
          <code className="font-mono text-xs text-muted">{p.tool}</code>
          {r.error && (
            <Badge tone="bad" className="ml-2">
              {String(r.error)}
            </Badge>
          )}
          <Json value={r} label="Result" />
        </div>
      );
    }
    case "injection_flag":
      return (
        <p className="text-xs text-bad">
          Matched: <span className="font-mono">{(p.patterns || []).join(", ")}</span>. The
          policy gate still decides.
        </p>
      );
    case "usage":
      return (
        <p className="font-mono text-[11px] text-subtle">
          in {p.input_tokens} · out {p.output_tokens}
        </p>
      );
    case "notice":
      return <p className="text-xs text-info">{p.message}</p>;
    case "output_correction":
      return <p className="text-xs text-bad">{p.reason}</p>;
    case "error":
      return <p className="text-xs text-bad">The model call failed ({p.error_type}).</p>;
    default:
      return <Json value={p} />;
  }
}

export default function ReasoningTimeline({
  steps,
  hideUsage = false,
}: {
  steps: StepEvent[];
  hideUsage?: boolean;
}) {
  const shown = hideUsage ? steps.filter((s) => s.step_type !== "usage") : steps;
  if (shown.length === 0) {
    return <p className="px-1 py-8 text-center text-sm text-subtle">No reasoning steps yet.</p>;
  }
  return (
    <ol className="relative space-y-3 before:absolute before:bottom-2 before:left-[13px] before:top-2 before:w-px before:bg-line">
      {shown.map((step) => {
        const meta = STEP_META[step.step_type] || STEP_META.tool_result;
        const Icon = meta.icon;
        return (
          <li key={`${step.id}-${step.seq}`} className="relative flex animate-fade-up gap-3">
            <span
              className={clsx(
                "relative z-10 mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full ring-4 ring-surface",
                DOT[meta.tone],
              )}
            >
              <Icon size={14} />
            </span>
            <div className="min-w-0 flex-1 pb-1">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[11px] font-semibold uppercase tracking-wide text-subtle">
                  {meta.label}
                </span>
                <span className="font-mono text-[10px] text-subtle">#{step.seq}</span>
              </div>
              <div className="mt-0.5">
                <StepBody step={step} />
              </div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
