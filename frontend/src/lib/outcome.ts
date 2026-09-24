import type { Outcome, StepEvent } from "../types";

// Tool errors that mean "not your order" (unknown ids look the same on purpose).
const BLOCKING_ERRORS = new Set(["ownership_mismatch", "identity_not_verified", "order_not_found"]);

/** Summarise what the deterministic gate decided during one agent turn. */
export function outcomeOf(steps: StepEvent[]): Outcome | null {
  let decided: Outcome | null = null; // issue_refund / escalate_to_human
  let evaluated: Outcome | null = null; // check_refund_eligibility
  let blocked = false;
  for (const s of steps) {
    const r = s.payload?.result;
    if (s.step_type === "decision" && r?.decision) decided = r.decision as Outcome;
    else if (s.step_type === "policy_eval" && r?.decision) evaluated = r.decision as Outcome;
    if (BLOCKING_ERRORS.has(r?.error)) blocked = true;
  }
  if (decided) return decided;
  if (blocked) return "blocked";
  // Eligibility said no and the agent (rightly) never tried to refund.
  if (evaluated === "denied" || evaluated === "escalated") return evaluated;
  if (steps.some((s) => s.step_type === "injection_flag")) return "flagged";
  return null;
}

export const OUTCOME_META: Record<Outcome, { label: string; tone: Tone }> = {
  approved: { label: "Refund approved", tone: "ok" },
  denied: { label: "Refund denied", tone: "bad" },
  escalated: { label: "Escalated to human", tone: "warn" },
  blocked: { label: "Access blocked", tone: "bad" },
  flagged: { label: "Injection flagged", tone: "warn" },
};

export type Tone = "ok" | "bad" | "warn" | "info" | "brand" | "neutral";

export const money = (n: number) =>
  n.toLocaleString(undefined, { style: "currency", currency: "USD" });
