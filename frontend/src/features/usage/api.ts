import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { z } from "zod";

import type { MeterTone } from "@/components/data/Meter";
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

const windowNameSchema = z.enum(["session", "week", "trial"]);

const windowSchema = z
  .object({
    used_share: z.number().min(0).max(1),
    limited: z.boolean(),
    exhausted: z.boolean(),
    resets_at: z.string().nullable(),
  })
  .transform((raw) => ({
    usedShare: raw.used_share,
    limited: raw.limited,
    exhausted: raw.exhausted,
    resetsAt: raw.resets_at,
  }));

const audioWindowSchema = z
  .object({
    used_seconds: z.number().int().nonnegative(),
    limit_seconds: z.number().int().positive().nullable(),
    exhausted: z.boolean(),
    resets_at: z.string().nullable(),
  })
  .transform((raw) => ({
    usedSeconds: raw.used_seconds,
    limitSeconds: raw.limit_seconds,
    // La stessa forma delle altre finestre: il pannello le disegna uguali.
    usedShare: raw.limit_seconds ? Math.min(1, raw.used_seconds / raw.limit_seconds) : 0,
    limited: raw.limit_seconds !== null,
    exhausted: raw.exhausted,
    resetsAt: raw.resets_at,
  }));

const enabledSchema = z
  .object({
    enabled: z.literal(true),
    session_hours: z.number().positive(),
    session: windowSchema,
    week: windowSchema,
    trial: z.intersection(windowSchema, z.object({ over: z.boolean() })),
    blocking: windowNameSchema.nullable(),
    forecast: z
      .object({ window: windowNameSchema, exhausts_at: z.string(), resets_at: z.string() })
      .nullable(),
    // Le ore di registrazione: un tetto separato dai modelli, in secondi.
    audio: z.object({
      week: audioWindowSchema,
      trial: audioWindowSchema,
      blocking: z.enum(["week", "trial"]).nullable(),
    }),
  })
  .transform((raw) => ({
    enabled: true as const,
    sessionHours: raw.session_hours,
    session: raw.session,
    week: raw.week,
    // Una prova finita e' esaurita, qualunque sia la sua quota: il pannello la
    // mostra piena e rossa senza casi speciali.
    trial: { ...raw.trial, exhausted: raw.trial.exhausted || raw.trial.over },
    trialOver: raw.trial.over,
    blocking: raw.blocking,
    forecast: raw.forecast
      ? { window: raw.forecast.window, exhaustsAt: raw.forecast.exhausts_at, resetsAt: raw.forecast.resets_at }
      : null,
    audio: raw.audio,
  }));

// Con i limiti spenti il backend non legge niente e manda il minimo.
const disabledSchema = z
  .object({ enabled: z.literal(false) })
  .transform(() => ({ enabled: false as const }));

const usageSchema = z.union([enabledSchema, disabledSchema]);

export type UsageWindowName = z.infer<typeof windowNameSchema>;
export type ActiveUsage = z.output<typeof enabledSchema>;
export type UsageWindow = ActiveUsage["session"];
export type AudioWindow = ActiveUsage["audio"]["week"];
export type Usage = z.output<typeof usageSchema>;

export async function fetchUsage(): Promise<Usage> {
  return usageSchema.parse(await http<unknown>("/v1/usage/me"));
}

/**
 * La quota che conta per l'anello: la finestra piu' vicina al limite.
 *
 * Un limite raggiunto vale sempre 1, anche quando la sua quota arrotondata non
 * lo dice: e' il caso in cui il consulente deve vedere il rosso.
 */
export function headlineShare(usage: ActiveUsage): number {
  if (usage.blocking) return 1;
  const shares = [usage.session, usage.week, usage.trial]
    .filter((window) => window.limited)
    .map((window) => window.usedShare);
  return shares.length ? Math.max(...shares) : 0;
}

/** I toni di `Meter`: ambra dall'80%, rosso dal 95%. */
export function usageTone(share: number): MeterTone {
  if (share >= 0.95) return "danger";
  if (share >= 0.8) return "warning";
  return "ok";
}

export function useUsageQuery(): UseQueryResult<Usage> {
  return useQuery({
    queryKey: usageKeys.me,
    queryFn: fetchUsage,
    // Il consumo cresce mentre il consulente lavora: un giro al minuto basta a
    // tenere l'anello vero. Con i limiti spenti si smette di chiedere.
    refetchInterval: (query) => (query.state.data?.enabled === false ? false : 60_000),
    staleTime: 20_000,
    retry: false,
  });
}
