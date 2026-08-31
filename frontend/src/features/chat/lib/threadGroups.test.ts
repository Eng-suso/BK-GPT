import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ChatSession } from "../types";
import { formatThreadTime, groupThreadsByRecency } from "./threadGroups";

function session(threadId: string, updatedAt: string): ChatSession {
  return { threadId, title: threadId, updatedAt, messages: [] };
}

const NOW = new Date("2026-08-31T12:00:00Z");

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(NOW);
});

afterEach(() => {
  vi.useRealTimers();
});

describe("groupThreadsByRecency", () => {
  it("buckets by recency, newest first, dropping empty buckets", () => {
    const groups = groupThreadsByRecency([
      session("today-early", "2026-08-31T08:00:00Z"),
      session("today-late", "2026-08-31T11:00:00Z"),
      session("yesterday", "2026-08-30T09:00:00Z"),
      session("older", "2026-01-01T09:00:00Z"),
    ]);

    expect(groups.map((g) => g.key)).toEqual(["today", "yesterday", "older"]);
    expect(groups[0].sessions.map((s) => s.threadId)).toEqual([
      "today-late",
      "today-early",
    ]);
  });

  it("puts timestamp-less sessions in older", () => {
    const groups = groupThreadsByRecency([
      { threadId: "no-date", title: "x", messages: [] },
    ]);
    expect(groups).toHaveLength(1);
    expect(groups[0].key).toBe("older");
  });

  it("returns nothing for an empty list", () => {
    expect(groupThreadsByRecency([])).toEqual([]);
  });
});

describe("formatThreadTime", () => {
  it("is empty for just-now and for unknown timestamps", () => {
    expect(formatThreadTime(session("a", NOW.toISOString()), "en")).toBe("");
    expect(formatThreadTime({ threadId: "b", title: "b", messages: [] }, "en")).toBe(
      "",
    );
  });

  it("uses a relative label within the hour", () => {
    expect(
      formatThreadTime(session("c", "2026-08-31T11:30:00Z"), "en"),
    ).toMatch(/30 min/);
  });

  it("uses a clock time earlier the same day", () => {
    expect(formatThreadTime(session("d", "2026-08-31T06:00:00Z"), "en")).toMatch(
      /\d/,
    );
  });
});
