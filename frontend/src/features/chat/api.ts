import { http, httpStream } from "@/lib/http";

import type { ApiChatScope, ChatMode } from "../../contracts/chat";
import type { BpmnReview, BpmnReviewVersion, ChatSession } from "./types";
import { normalizeSession, type RawSession } from "./lib/normalizeSession";

/**
 * Backend seam for the chat feature. Components never call `fetch` — hooks build
 * TanStack Query queries/mutations on top of these functions. See
 * docs/frontend-stack.md.
 */

export const chatKeys = {
  all: ["chat"] as const,
  sessions: (scopeKey: string) => [...chatKeys.all, "sessions", scopeKey] as const,
  session: (threadId: string) => [...chatKeys.all, "session", threadId] as const,
  review: (bpmnModelId: string) => [...chatKeys.all, "review", bpmnModelId] as const,
  reviewVersions: (bpmnModelId: string) =>
    [...chatKeys.all, "review-versions", bpmnModelId] as const,
};

const SESSIONS_BASE = "/v1/consultant-chat/sessions";

export async function fetchChatSessions(scopeKey: string): Promise<ChatSession[]> {
  const params = new URLSearchParams({ scope_key: scopeKey });
  const data = await http<RawSession[]>(`${SESSIONS_BASE}?${params}`);
  return data.map(normalizeSession);
}

export async function fetchChatSession(threadId: string): Promise<ChatSession> {
  const data = await http<RawSession>(`${SESSIONS_BASE}/${threadId}`);
  return normalizeSession(data);
}

export async function createChatSession(input: {
  modelName: string;
  scope: ApiChatScope;
}): Promise<ChatSession> {
  const data = await http<RawSession>(SESSIONS_BASE, {
    method: "POST",
    body: { model_name: input.modelName, scope: input.scope },
  });
  return normalizeSession(data);
}

export function deleteChatSession(threadId: string): Promise<void> {
  return http<void>(`${SESSIONS_BASE}/${threadId}`, {
    method: "DELETE",
    admin: true,
  });
}

export function clearChatSessions(scopeKey: string): Promise<void> {
  const params = new URLSearchParams({ scope_key: scopeKey });
  return http<void>(`${SESSIONS_BASE}?${params}`, {
    method: "DELETE",
    admin: true,
  });
}

export async function transcribeAudio(file: File): Promise<string> {
  const formData = new FormData();
  formData.append("file", file);
  // No `language` field on purpose: the expected interview language is a
  // deployment setting (`openai_transcription_language`), not a UI constant.

  const data = await http<{ text?: string }>("/v1/audio/transcriptions", {
    method: "POST",
    body: formData,
  });
  return String(data.text || "").trim();
}

/** Opens the NDJSON stream; the caller reads `response.body`. */
export function streamChatMessage(
  threadId: string,
  input: {
    message: string;
    modelName: string;
    scope: ApiChatScope;
    mode: ChatMode;
  },
): Promise<Response> {
  return httpStream(`${SESSIONS_BASE}/${threadId}/messages/stream`, {
    method: "POST",
    body: {
      message: input.message,
      model_name: input.modelName,
      scope: input.scope,
      mode: input.mode,
    },
  });
}

/**
 * Pending BPMN review for a canvas scope. The backend returns `200` with a
 * `null` body when nothing is waiting; a real failure (5xx / network) propagates
 * so the caller surfaces it instead of silently showing an empty state.
 */
export function fetchBpmnReview(
  bpmnModelId: string,
): Promise<BpmnReview | null> {
  return http<BpmnReview | null>(
    `/v1/workspace/bpmn-models/${bpmnModelId}/review`,
    { cache: "no-store" },
  );
}

export function approveBpmnReview(bpmnModelId: string): Promise<void> {
  return http<void>(
    `/v1/workspace/bpmn-models/${bpmnModelId}/review/approve`,
    { method: "POST" },
  );
}

/** Every recorded state of the plan, newest first. */
export function fetchBpmnReviewVersions(
  bpmnModelId: string,
): Promise<BpmnReviewVersion[]> {
  return http<BpmnReviewVersion[]>(
    `/v1/workspace/bpmn-models/${bpmnModelId}/review/versions`,
    { cache: "no-store" },
  );
}

/** Record what the consultant decided about one open question. */
export function answerBpmnReviewQuestion(
  bpmnModelId: string,
  input: { question: string; answer: string },
): Promise<BpmnReview> {
  return http<BpmnReview>(
    `/v1/workspace/bpmn-models/${bpmnModelId}/review/answers`,
    { method: "POST", body: input },
  );
}

export function saveBpmnReview(
  bpmnModelId: string,
  bpmnBrief: string,
): Promise<BpmnReview> {
  return http<BpmnReview>(
    `/v1/workspace/bpmn-models/${bpmnModelId}/review`,
    {
      method: "PUT",
      body: { bpmn_brief: bpmnBrief },
    },
  );
}
