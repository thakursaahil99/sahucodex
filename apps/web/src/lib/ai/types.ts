export type AiFeature = "hint" | "explain" | "review";

export interface AiStatus {
  configured: boolean;
  model: string | null;
}

/** A one-off generation (Hint / Explain / Review). Never a verdict — see the AI tab's banner. */
export interface Generation {
  feature: AiFeature | "chat";
  content: string;
  model: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export interface ConversationSummary {
  id: string;
  title: string;
  problem_slug: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConversationDetail extends ConversationSummary {
  messages: ChatMessage[];
}

/** What the server streams back, already parsed from Server-Sent Events. */
export type StreamEvent =
  | { type: "start"; conversationId: string }
  | { type: "token"; content: string }
  | { type: "done" }
  | { type: "error"; code: string; message: string };
