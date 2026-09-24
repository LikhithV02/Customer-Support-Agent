export interface StepEvent {
  kind: "step";
  id: number;
  seq: number;
  step_type:
    | "model"
    | "tool_call"
    | "tool_result"
    | "policy_eval"
    | "decision"
    | "injection_flag"
    | "usage"
    | "budget_exhausted"
    | "output_correction"
    | "notice"
    | "error";
  node: string;
  payload: Record<string, any>;
  created_at: string;
}

export interface MessageEvent {
  kind: "message";
  role: "user" | "assistant";
  content: string;
}

export interface ConversationEvent {
  kind: "conversation";
  conversation_id: string;
}

export interface DoneEvent {
  kind: "done";
}

export interface ErrorEvent {
  kind: "error";
  message: string;
}

export type AgentEvent =
  | StepEvent
  | MessageEvent
  | ConversationEvent
  | DoneEvent
  | ErrorEvent;

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  at: number;
  /** Outcome of the turn this assistant message closed (see outcomeOf). */
  outcome?: Outcome | null;
  error?: boolean;
}

export type Outcome = "approved" | "denied" | "escalated" | "blocked" | "flagged";

export interface ConversationSummary {
  id: string;
  customer_id: string | null;
  customer_name: string | null;
  created_at: string;
  message_count: number;
  last_message: string | null;
}

export interface ConversationDetail {
  id: string;
  customer_id: string | null;
  customer_name: string | null;
  messages: { id: number; role: string; content: string; created_at: string }[];
  events: StepEvent[];
}

export type Scenario =
  | "refundable"
  | "final_sale"
  | "high_value"
  | "out_of_window"
  | "already_refunded";

export interface Order {
  id: string;
  product_name: string;
  amount: number;
  status: string;
  order_date: string | null;
  delivered_date: string | null;
  is_final_sale: boolean;
  refunded: boolean;
  scenario: Scenario | null;
}

export interface DemoSession {
  customer: { id: string; name: string; email: string };
  orders: Order[];
  token: string;
  admin_token: string;
  expires_in: number;
  data_ttl_hours: number;
}

export interface Meta {
  auth_mode: "dev" | "jwt" | "demo";
  model: string;
  demo: { session_ttl_s: number; data_ttl_hours: number } | null;
}

export interface AdminStats {
  conversations: number;
  messages: number;
  decisions: Record<string, number>;
  injection_flags: number;
  tokens_used: number;
}
