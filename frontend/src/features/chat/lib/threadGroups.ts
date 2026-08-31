import type { ChatSession } from "../types";

export type ThreadGroupKey = "today" | "yesterday" | "last7" | "older";

export interface ThreadGroup {
  key: ThreadGroupKey;
  sessions: ChatSession[];
}

const DAY_MS = 86_400_000;

const GROUP_ORDER: ThreadGroupKey[] = ["today", "yesterday", "last7", "older"];

function threadTimestamp(session: ChatSession): number {
  const raw = session.updatedAt || session.createdAt || "";
  const ms = raw ? Date.parse(raw) : Number.NaN;
  return Number.isNaN(ms) ? 0 : ms;
}

function startOfDay(ms: number): number {
  const d = new Date(ms);
  d.setHours(0, 0, 0, 0);
  return d.getTime();
}

/**
 * Bucket sessions by recency (Today / Yesterday / Last 7 days / Older), newest
 * first inside each bucket. Empty buckets are dropped. Sessions with no usable
 * timestamp fall into "older".
 */
export function groupThreadsByRecency(sessions: ChatSession[]): ThreadGroup[] {
  const todayStart = startOfDay(Date.now());
  const buckets: Record<ThreadGroupKey, ChatSession[]> = {
    today: [],
    yesterday: [],
    last7: [],
    older: [],
  };

  for (const session of sessions) {
    const ts = threadTimestamp(session);
    if (ts >= todayStart) buckets.today.push(session);
    else if (ts >= todayStart - DAY_MS) buckets.yesterday.push(session);
    else if (ts >= todayStart - 7 * DAY_MS) buckets.last7.push(session);
    else buckets.older.push(session);
  }

  for (const key of GROUP_ORDER) {
    buckets[key].sort((a, b) => threadTimestamp(b) - threadTimestamp(a));
  }

  return GROUP_ORDER.filter((key) => buckets[key].length > 0).map((key) => ({
    key,
    sessions: buckets[key],
  }));
}

/** Short, locale-aware "when" label for a thread row. Empty when unknown/just now. */
export function formatThreadTime(session: ChatSession, locale: string): string {
  const ts = threadTimestamp(session);
  if (!ts) return "";

  const diffMs = Date.now() - ts;
  if (diffMs < 60_000) return "";

  if (diffMs < 3_600_000) {
    const minutes = Math.max(1, Math.round(diffMs / 60_000));
    return new Intl.RelativeTimeFormat(locale, { numeric: "auto" }).format(
      -minutes,
      "minute",
    );
  }

  const todayStart = startOfDay(Date.now());
  if (ts >= todayStart) {
    return new Intl.DateTimeFormat(locale, {
      hour: "2-digit",
      minute: "2-digit",
    }).format(ts);
  }
  if (ts >= todayStart - 6 * DAY_MS) {
    return new Intl.DateTimeFormat(locale, { weekday: "short" }).format(ts);
  }
  return new Intl.DateTimeFormat(locale, {
    day: "2-digit",
    month: "short",
  }).format(ts);
}
