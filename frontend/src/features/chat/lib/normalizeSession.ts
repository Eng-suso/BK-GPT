import type { ChatMessage, ChatSession } from "../types";

export type RawMessage = {
  id?: string | number;
  role?: string;
  content?: string;
  created_at?: string;
  createdAt?: string;
};

export type RawSession = {
  thread_id?: string;
  threadId?: string;
  title?: string;
  model_name?: string;
  modelName?: string;
  created_at?: string;
  createdAt?: string;
  updated_at?: string;
  updatedAt?: string;
  message_count?: number;
  messages?: RawMessage[];
};

/** A conversation title derived from its first user message. */
export function sessionTitle(message: string): string {
  const clean = message.trim().replace(/\s+/g, " ");
  return clean.length > 28 ? `${clean.slice(0, 28)}...` : clean || "Nuova chat";
}

/** Map a backend session payload (snake or camel) to the client shape. */
export function normalizeSession(session: RawSession): ChatSession {
  return {
    threadId: session.thread_id || session.threadId || "",
    title: session.title || "Nuova chat",
    modelName: session.model_name || session.modelName || null,
    createdAt: session.created_at || session.createdAt || "",
    updatedAt: session.updated_at || session.updatedAt || "",
    messageCount:
      session.message_count || (session.messages ? session.messages.length : 0),
    messages: (session.messages || []).map((m) => ({
      id: String(m.id || ""),
      role: (m.role as ChatMessage["role"]) || "user",
      content: m.content || "",
      createdAt: m.created_at || m.createdAt,
    })),
  };
}
