import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ChatScope } from "../../../contracts/chat";
import type { ChatSession } from "../types";

const fetchChatSessions = vi.fn<(scopeKey: string) => Promise<ChatSession[]>>();

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    fetchChatSessions: (scopeKey: string) => fetchChatSessions(scopeKey),
    fetchChatSession: vi.fn(),
    createChatSession: vi.fn(),
    deleteChatSession: vi.fn(),
    clearChatSessions: vi.fn(),
  };
});

const { useChatSessions } = await import("./useChatSessions");

function session(threadId: string): ChatSession {
  return { threadId, title: threadId, updatedAt: "2026-01-01", messages: [] };
}

function wrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

const scopeA: ChatScope = { type: "project", projectId: "A", projectName: "A" };
const scopeB: ChatScope = { type: "project", projectId: "B", projectName: "B" };

afterEach(() => {
  vi.clearAllMocks();
});

describe("useChatSessions — scope race", () => {
  it("a slow response for the previous scope never lands on the new scope", async () => {
    let resolveA: (value: ChatSession[]) => void = () => {};
    fetchChatSessions.mockImplementation((scopeKey) => {
      if (scopeKey === "project:A") {
        return new Promise<ChatSession[]>((resolve) => {
          resolveA = resolve;
        });
      }
      return Promise.resolve([session("B-1")]);
    });

    const { result, rerender } = renderHook(
      ({ scope }: { scope: ChatScope }) => useChatSessions(scope, "model"),
      { initialProps: { scope: scopeA }, wrapper: wrapper() },
    );

    expect(result.current.scopeKey).toBe("project:A");

    // Switch scope while scope A's request is still in flight.
    rerender({ scope: scopeB });
    await waitFor(() => {
      expect(result.current.sessions).toEqual([session("B-1")]);
    });
    expect(result.current.scopeKey).toBe("project:B");
    expect(result.current.currentThreadId).toBe("B-1");

    // Scope A finally answers — with stale data — and must be ignored.
    resolveA([session("A-1"), session("A-2")]);
    await new Promise((r) => setTimeout(r, 10));

    expect(result.current.sessions).toEqual([session("B-1")]);
    expect(result.current.currentThreadId).toBe("B-1");
  });

  it("auto-selects the newest thread once, and honours an explicit new-thread", async () => {
    fetchChatSessions.mockResolvedValue([session("t1"), session("t2")]);

    const { result } = renderHook(
      () => useChatSessions(scopeA, "model"),
      { wrapper: wrapper() },
    );

    await waitFor(() => expect(result.current.currentThreadId).toBe("t1"));

    result.current.startNewThread();
    await waitFor(() => expect(result.current.currentThreadId).toBeNull());
  });
});
