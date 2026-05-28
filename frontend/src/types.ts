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
  role: "user" | "assistant";
  content: string;
}

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
