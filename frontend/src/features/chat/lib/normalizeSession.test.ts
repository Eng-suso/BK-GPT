import { describe, expect, it } from "vitest";

import { normalizeSession, sessionTitle } from "./normalizeSession";

describe("normalizeSession", () => {
  it("reads snake_case fields from the backend payload", () => {
    const session = normalizeSession({
      thread_id: "t1",
      title: "Preventivo",
      model_name: "gpt-5.6-luna",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-02T00:00:00Z",
      message_count: 2,
      messages: [
        { id: 1, role: "user", content: "ciao", created_at: "2026-01-01" },
        { id: 2, role: "assistant", content: "salve" },
      ],
    });

    expect(session).toMatchObject({
      threadId: "t1",
      title: "Preventivo",
      modelName: "gpt-5.6-luna",
      updatedAt: "2026-01-02T00:00:00Z",
      messageCount: 2,
    });
    expect(session.messages).toHaveLength(2);
    expect(session.messages[0]).toEqual({
      id: "1",
      role: "user",
      content: "ciao",
      createdAt: "2026-01-01",
    });
  });

  it("also accepts camelCase and fills sensible defaults", () => {
    const session = normalizeSession({ threadId: "t2" });
    expect(session.threadId).toBe("t2");
    expect(session.title).toBe("Nuova chat");
    expect(session.modelName).toBeNull();
    expect(session.messageCount).toBe(0);
    expect(session.messages).toEqual([]);
  });

  it("derives messageCount from the messages array when absent", () => {
    const session = normalizeSession({
      threadId: "t3",
      messages: [
        { role: "user", content: "a" },
        { role: "assistant", content: "b" },
        { role: "user", content: "c" },
      ],
    });
    expect(session.messageCount).toBe(3);
  });
});

describe("sessionTitle", () => {
  it("collapses whitespace and keeps short prompts intact", () => {
    expect(sessionTitle("  Ciao   mondo ")).toBe("Ciao mondo");
  });

  it("truncates long prompts with an ellipsis", () => {
    expect(sessionTitle("a".repeat(40))).toBe(`${"a".repeat(28)}...`);
  });

  it("falls back to a default for an empty prompt", () => {
    expect(sessionTitle("   ")).toBe("Nuova chat");
  });
});
