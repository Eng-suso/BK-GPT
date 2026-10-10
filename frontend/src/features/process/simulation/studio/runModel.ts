/**
 * The Simulation IR a run actually simulated (SIM-20a) —
 * `GET /v1/workspace/simulation-runs/{id}/model`, `backend/simulation/ir/model.py`.
 *
 * Only what the inspector reads is validated; unknown keys pass through, so a
 * richer IR does not break the screen. `model` is null for runs created before
 * the model was kept: the inspector then falls back on the v1 request.
 */

import { useQuery } from "@tanstack/react-query";
import { z } from "zod";

import { http } from "@/lib/http";

import { parameterProvenanceSchema } from "../simulationTypes";

const bounded = { minimum: z.number(), maximum: z.number() };

export const irDistributionSchema = z.discriminatedUnion("kind", [
  z.object({ kind: z.literal("fixed"), value: z.number() }),
  z.object({ kind: z.literal("exponential"), mean: z.number(), ...bounded }),
  z.object({ kind: z.literal("uniform"), ...bounded }),
  z.object({ kind: z.literal("normal"), mean: z.number(), std: z.number(), ...bounded }),
  z.object({ kind: z.literal("lognormal"), mean: z.number(), variance: z.number(), ...bounded }),
  z.object({ kind: z.literal("gamma"), mean: z.number(), variance: z.number(), ...bounded }),
]);
export type IrDistribution = z.infer<typeof irDistributionSchema>;

const provenance = parameterProvenanceSchema.nullable().optional();

const ruleSchema = z.object({
  attribute: z.string(),
  operator: z.enum([">", ">=", "<", "<=", "=", "!="]),
  value: z.union([z.string(), z.number()]),
});
export type IrRule = z.infer<typeof ruleSchema>;

export const runModelSchema = z.object({
  arrival: z.object({ interarrival: irDistributionSchema, calendar_id: z.string(), provenance }).optional(),
  priority_rules: z.array(z.object({ level: z.number(), condition: z.object({ any_of: z.array(z.array(ruleSchema)) }) })).optional(),
  calendars: z.array(
    z.object({
      id: z.string(),
      name: z.string(),
      periods: z.array(z.object({ from_day: z.string(), to_day: z.string(), begin: z.string(), end: z.string() })),
    }),
  ),
  pools: z.array(
    z.object({
      id: z.string(),
      name: z.string(),
      resources: z.array(
        z.object({
          id: z.string(),
          name: z.string(),
          cost_per_hour: z.number(),
          amount: z.number(),
          calendar_id: z.string(),
          provenance,
        }),
      ),
    }),
  ),
  activities: z.array(
    z.object({
      element_id: z.string(),
      name: z.string().default(""),
      assignments: z.array(z.object({ resource_id: z.string(), duration: irDistributionSchema, provenance })),
    }),
  ),
  gateways: z
    .array(
      z.object({
        element_id: z.string(),
        branches: z.array(
          z.object({
            flow_id: z.string(),
            probability: z.number(),
            condition: z.object({ any_of: z.array(z.array(ruleSchema)) }).nullable().optional(),
            provenance,
          }),
        ),
      }),
    )
    .default([]),
});
export type RunModel = z.infer<typeof runModelSchema>;

export const runModelResponseSchema = z.object({
  run_id: z.number(),
  model: runModelSchema.nullable(),
});

export async function fetchRunModel(runId: number): Promise<RunModel | null> {
  const raw = await http<unknown>(`/v1/workspace/simulation-runs/${runId}/model`);
  return runModelResponseSchema.parse(raw).model;
}

/** A run's model never changes once created: cache it for good. */
export function useRunModel(runId: number, enabled = true) {
  return useQuery({
    queryKey: ["workspace", "simulation-run-model", runId],
    queryFn: () => fetchRunModel(runId),
    enabled,
    staleTime: Infinity,
  });
}
