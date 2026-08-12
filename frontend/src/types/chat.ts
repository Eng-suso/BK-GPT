export type MessageRole = "user" | "assistant" | "system" | "error";

export interface ChatMessage {
  id?: number | string;
  role: MessageRole;
  content: string;
  createdAt?: string;
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
