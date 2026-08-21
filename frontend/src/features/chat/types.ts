export type MessageRole = "user" | "assistant" | "system" | "error";

export type AgentActivityStatus = "running" | "completed";

export interface AgentActivity {
  key: string;
  label: string;
  status: AgentActivityStatus;
}

export interface ChatMessage {
  id?: number | string;
  role: MessageRole;
  content: string;
  createdAt?: string;
  activity?: AgentActivity[];
}

export type ChatStatus = "idle" | "sending" | "streaming" | "error";

export interface ChatSession {
  threadId: string;
  title: string;
  modelName?: string | null;
  createdAt?: string;
  updatedAt?: string;
  messageCount?: number;
  messages: ChatMessage[];
}

export interface PromptSuggestion {
  icon: string;
  title: string;
  description: string;
  prompt: string;
}
