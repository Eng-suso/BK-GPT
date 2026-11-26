import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { z } from "zod";

import { http } from "@/lib/http";

/**
 * Backend seam for the usage meter. Components never call `fetch`.
 *
 * Il backend manda quote e orari, mai importi: al consulente serve sapere
 * quanto gli resta e quando si ripristina, non quanto costa un token.
 */

export const usageKeys = {
  me: ["usage-me"] as const,
};

const windowSchema = z.object({
  used_share: z.number().min(0).max(1),
  limited: z.boolean(),
  exhausted: z.boolean(),
  started_at: z.string().nullable(),
  resets_at: z.string().nullable(),
});

const usageSchema = z.object({
  enabled: z.boolean(),
  session: windowSchema,
  week: windowSchema,
  trial: windowSchema.extend({ over: z.boolean() }),
  blocking: z.enum(["session", "week", "trial"]).nullable(),
  forecast: z
    .object({
      window: z.enum(["session", "week", "trial"]),
      exhausts_at: z.string(),
      resets_at: z.string(),
    })
    .nullable(),
});

export type UsageWindowName = "session" | "week" | "trial";

export type UsageWindow = {
  usedShare: number;
  limited: boolean;
  exhausted: boolean;
  startedAt: string | null;
  resetsAt: string | null;
};

export type Usage = {
  enabled: boolean;
  session: UsageWindow;
  week: UsageWindow;
  trial: UsageWindow & { over: boolean };
  blocking: UsageWindowName | null;
  forecast: { window: UsageWindowName; exhaustsAt: string; resetsAt: string } | null;
};

function toWindow(raw: z.infer<typeof windowSchema>): UsageWindow {
  return {
    usedShare: raw.used_share,
    limited: raw.limited,
    exhausted: raw.exhausted,
    startedAt: raw.started_at,
    resetsAt: raw.resets_at,
  };
}

export async function fetchUsage(): Promise<Usage> {
  const raw = usageSchema.parse(await http<unknown>("/v1/usage/me"));
  return {
    enabled: raw.enabled,
    session: toWindow(raw.session),
    week: toWindow(raw.week),
    trial: { ...toWindow(raw.trial), over: raw.trial.over },
    blocking: raw.blocking,
    forecast: raw.forecast
      ? { window: raw.forecast.window, exhaustsAt: raw.forecast.exhausts_at, resetsAt: raw.forecast.resets_at }
      : null,
  };
}

/**
 * La quota che conta per l'anello: la finestra piu' vicina al limite.
 *
 * Un limite raggiunto vale sempre 1, anche quando la sua quota arrotondata non
 * lo dice: e' il caso in cui il consulente deve vedere il rosso.
 */
export function headlineShare(usage: Usage): number {
  if (usage.blocking) return 1;
  const shares = [usage.session, usage.week, usage.trial]
    .filter((window) => window.limited)
    .map((window) => window.usedShare);
  return shares.length ? Math.max(...shares) : 0;
}

export type UsageTone = "normal" | "warning" | "danger";

export function usageTone(share: number): UsageTone {
  if (share >= 0.95) return "danger";
  if (share >= 0.8) return "warning";
  return "normal";
}

export function useUsageQuery(): UseQueryResult<Usage> {
  return useQuery({
    queryKey: usageKeys.me,
    queryFn: fetchUsage,
    // Il consumo cresce mentre il consulente lavora: un giro al minuto basta a
    // tenere l'anello vero senza pesare sul backend.
    refetchInterval: 60_000,
    staleTime: 20_000,
    retry: false,
  });
}
