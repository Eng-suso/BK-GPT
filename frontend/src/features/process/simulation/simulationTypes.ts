import { z } from "zod";

/**
 * Full-log KPI summary attached to a completed run (Phase 1). Kept loose for now —
 * Phase 5+ screens will pin the exact shape as they consume each field. Backend
 * contract: backend/simulation/log_processor.py `_build_summary`.
 */
export const simulationSummarySchema = z
  .object({
    casesCompleted: z.number(),
    cycle: z.object({ avg: z.number(), p50: z.number(), p90: z.number(), p95: z.number() }),
    waiting: z.object({ avg: z.number(), p95: z.number(), share: z.number() }),
    processing: z.object({ avg: z.number(), p95: z.number().optional() }),
    cost: z.object({ total: z.number(), perCase: z.number() }),
    throughputPerHour: z.number(),
    byActivity: z.array(z.record(z.string(), z.unknown())),
    byResource: z.array(z.record(z.string(), z.unknown())),
    bottleneck: z.record(z.string(), z.unknown()).nullable(),
  })
  .loose();

export type SimulationSummary = z.infer<typeof simulationSummarySchema>;

export const simulationRunSchema = z.object({
  id: z.number(),
  bpmn_model_id: z.string(),
  process_id: z.string(),
  scenario_name: z.string(),
  engine: z.string(),
  status: z.enum(["pending", "completed", "failed"]),
  idempotency_key: z.string().nullable().optional(),
  request: z.record(z.string(), z.unknown()),
  scenario: z.record(z.string(), z.unknown()),
  result: z.record(z.string(), z.unknown()),
  outputs: z.array(z.string()),
  summary: simulationSummarySchema.nullable().optional(),
  error: z.string().nullable(),
  created_at: z.string(),
  completed_at: z.string().nullable(),
});

/**
 * Heavy display artifact — sampled case paths + bucketed series + flow volumes.
 * Fetched only by the replay/dashboard screens, never with the run. Backend:
 * `_build_replay` + GET /v1/workspace/simulation-runs/{id}/replay.
 */
export const simulationReplaySchema = z.object({
  run_id: z.number(),
  schema_version: z.number(),
  replay: z
    .object({
      schemaVersion: z.number(),
      meta: z.object({
        start: z.string(),
        durationSec: z.number(),
        totalCases: z.number(),
        sampledCases: z.number(),
        bucketSec: z.number(),
      }),
      elements: z.record(z.string(), z.object({ name: z.string() })),
      cases: z.array(
        z.object({
          id: z.string(),
          cycleSec: z.number(),
          events: z.array(
            z.object({
              el: z.string().nullable(),
              enable: z.number(),
              start: z.number(),
              end: z.number(),
              res: z.string(),
            }),
          ),
        }),
      ),
      series: z.object({
        t: z.array(z.number()),
        byElement: z.record(
          z.string(),
          z.object({
            active: z.array(z.number()),
            queued: z.array(z.number()),
            done: z.array(z.number()),
          }),
        ),
        byResource: z.record(z.string(), z.object({ busy: z.array(z.number()) })),
        global: z.record(z.string(), z.array(z.number())),
      }),
      flows: z.record(
        z.string(),
        z.object({ count: z.number(), attributed: z.boolean() }),
      ),
    })
    .loose(),
});

export type SimulationReplay = z.infer<typeof simulationReplaySchema>;

export const simulationRunsSchema = z.array(simulationRunSchema);

export type SimulationRun = z.infer<typeof simulationRunSchema>;

export const scenarioTemplateSchema = z.object({
  tasks: z.array(
    z.object({ element_id: z.string(), name: z.string(), type: z.string() }),
  ),
  gateways: z.array(
    z.object({
      element_id: z.string(),
      name: z.string(),
      type: z.string(),
      branches: z.array(
        z.object({
          flow_id: z.string(),
          flow_name: z.string(),
          target_name: z.string(),
        }),
      ),
    }),
  ),
});

export type ScenarioTemplate = z.infer<typeof scenarioTemplateSchema>;
export type ScenarioTemplateTask = ScenarioTemplate["tasks"][number];
export type ScenarioTemplateGateway = ScenarioTemplate["gateways"][number];

/**
 * Structural provenance for the scenario builder (Phase 5). Says where each
 * simulable element came from — discovery evidence or a model inference — so the
 * consultant knows how far to trust the parameter they set for it. Backend:
 * `backend/simulation/provenance.py`.
 */
export const scenarioProvenanceSchema = z.object({
  has_discovery: z.boolean(),
  process_confidence: z.enum(["high", "medium", "low"]).nullable().optional(),
  readiness_score: z.number().nullable().optional(),
  missing_information: z.array(z.string()).default([]),
  weak_points: z.array(z.string()).default([]),
  elements: z.array(
    z.object({
      element_id: z.string(),
      kind: z.enum(["activity", "gateway"]),
      name: z.string(),
      parameter: z.enum(["duration", "branching"]),
      origin: z.enum(["interview", "ai_inferred"]),
      confidence: z.enum(["high", "medium", "low"]),
      evidence: z.array(z.string()).default([]),
      open_questions: z.number().default(0),
      hint_ref: z
        .object({
          field: z.string(),
          id: z.string().nullable().optional(),
          label: z.string().nullable().optional(),
        })
        .nullable()
        .optional(),
    }),
  ),
});

export type ScenarioProvenance = z.infer<typeof scenarioProvenanceSchema>;
export type ScenarioElementProvenance = ScenarioProvenance["elements"][number];

/**
 * Heuristic experiment suggestions for a completed run (Phase 9). Backend:
 * `backend/simulation/advisor.py` — no LLM, M/M/c waiting-time ratio.
 */
export const experimentReportSchema = z.object({
  bottleneck_el: z.string().nullable().optional(),
  bottleneck_name: z.string().nullable().optional(),
  factors: z.record(z.string(), z.number()).default({}),
  experiments: z.array(
    z.object({
      kind: z.literal("add_resource"),
      pool_id: z.string(),
      pool_name: z.string(),
      from_amount: z.number(),
      to_amount: z.number(),
      rationale: z.string(),
      estimate: z.object({ cycle_pct: z.number(), cost_pct: z.number() }),
      target_el: z.string().nullable().optional(),
    }),
  ),
});

export type ExperimentReport = z.infer<typeof experimentReportSchema>;
export type Experiment = ExperimentReport["experiments"][number];

export type SimResourceInput = {
  id: string;
  name: string;
  costPerHour: number;
  amount: number;
};

export type SimTaskInput = {
  elementId: string;
  meanSeconds: number;
  distribution: "norm" | "expon" | "fixed";
  resourceId: string | null;
};

export type SimGatewayInput = {
  elementId: string;
  branches: { flowId: string; probability: number }[];
};

export type CreateSimulationRunInput = {
  scenarioName: string;
  totalCases: number;
  currentBpmnXml: string | null;
  arrivalIntervalSeconds: number;
  defaultTaskDurationSeconds: number;
  defaultCostPerHour: number;
  resourceAmount: number;
  resourceName: string;
  resources?: SimResourceInput[];
  tasks?: SimTaskInput[];
  gateways?: SimGatewayInput[];
  idempotencyKey?: string;
};
