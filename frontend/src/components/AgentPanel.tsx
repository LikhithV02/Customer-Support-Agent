import { Activity } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { OUTCOME_META, outcomeOf } from "../lib/outcome";
import type { StepEvent } from "../types";
import ReasoningTimeline from "./ReasoningTimeline";
import { Badge, LiveDot } from "./ui";

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg bg-surface-2 px-2.5 py-2">
      <div className="text-[10px] font-medium uppercase tracking-wide text-subtle">{label}</div>
      <div className="mt-0.5 font-mono text-sm font-semibold tabular-nums">{value}</div>
    </div>
  );
}

/** Live view of the current (or last) agent turn: stats plus the step timeline. */
export default function AgentPanel({
  steps,
  streaming,
  startedAt,
  endedAt,
  showTitle = true,
}: {
  steps: StepEvent[];
  streaming: boolean;
  startedAt: number | null;
  endedAt: number | null;
  showTitle?: boolean;
}) {
  const [now, setNow] = useState(Date.now());
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!streaming) return;
    const t = setInterval(() => setNow(Date.now()), 100);
    return () => clearInterval(t);
  }, [streaming]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [steps.length]);

  const tokens = steps
    .filter((s) => s.step_type === "usage")
    .reduce((n, s) => n + (s.payload.input_tokens ?? 0) + (s.payload.output_tokens ?? 0), 0);
  const tools = steps.filter((s) => s.step_type === "tool_call").length;
  const elapsed = startedAt ? ((streaming ? now : endedAt ?? now) - startedAt) / 1000 : 0;
  const outcome = outcomeOf(steps);

  return (
    <div className="flex h-full flex-col">
      <div className="space-y-3 border-b border-line p-4">
        <div className="flex items-center justify-between">
          {showTitle ? (
            <div className="flex items-center gap-2 text-sm font-semibold">
              <Activity size={16} className="text-brand" /> Agent reasoning
            </div>
          ) : (
            <span className="text-xs text-subtle">Latest turn</span>
          )}
          {streaming ? (
            <span className="flex items-center gap-1.5 text-[11px] font-semibold text-bad">
              <LiveDot /> LIVE
            </span>
          ) : outcome ? (
            <Badge tone={OUTCOME_META[outcome].tone}>{OUTCOME_META[outcome].label}</Badge>
          ) : null}
        </div>
        <div className="grid grid-cols-3 gap-2">
          <Stat label="Tool calls" value={tools} />
          <Stat label="Tokens" value={tokens.toLocaleString()} />
          <Stat label="Elapsed" value={`${elapsed.toFixed(1)}s`} />
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {steps.length === 0 && !streaming ? (
          <div className="px-2 py-10 text-center">
            <p className="text-sm font-medium">Nothing to show yet</p>
            <p className="mt-1 text-xs text-subtle">
              Send a message and each tool call, policy check and decision will stream in here.
            </p>
          </div>
        ) : (
          <ReasoningTimeline steps={steps} hideUsage />
        )}
        <div ref={endRef} />
      </div>
    </div>
  );
}
