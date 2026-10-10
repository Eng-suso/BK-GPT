import type { ModelPatchInput } from "./caseRules";
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
    cost: z.object({
      total: z.number(),
      perCase: z.number(),
      /** SIM-10: presente solo se lo scenario aveva costi fissi. */
      breakdown: z.object({ resources: z.number(), activities: z.number(), cases: z.number() }).optional(),
    }),
    /** SIM-03: quanti casi del riscaldamento sono rimasti fuori dai KPI. */
    warmup: z.object({ excludedCases: z.number(), measuredCases: z.number() }).optional(),
    /** SIM-13: l'esito dell'obiettivo di servizio, se lo scenario ne aveva uno. */
    sla: z.object({
      target_seconds: z.number(),
      share_target: z.number(),
      share_within: z.number(),
      cases: z.number(),
      late_cases: z.number(),
      met: z.boolean(),
    }).nullable().optional(),
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
  /** P0.3: per un run in attesa, in coda (con la posizione) o in corso. */
  queue: z
    .object({ state: z.enum(["queued", "running"]), position: z.number().nullable() })
    .nullable()
    .optional(),
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

export const scenarioTemplateResourceSchema = z.object({
  id: z.string(), name: z.string(), kind: z.enum(["pool", "lane"]),
  bpmn_id: z.string(), pool_name: z.string().nullable().optional(),
  parent_name: z.string().nullable().optional(), task_ids: z.array(z.string()),
});
export type ScenarioTemplateResource = z.infer<typeof scenarioTemplateResourceSchema>;

/** Le distribuzioni che Prosimos 2.1 esegue: niente triangolare, Weibull o Beta. */
export const DISTRIBUTIONS = ["fixed", "expon", "uniform", "norm", "lognorm", "gamma"] as const;
export type DistributionName = (typeof DISTRIBUTIONS)[number];

export const WEEKDAYS = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"] as const;
export type Weekday = (typeof WEEKDAYS)[number];

export const simCalendarSchema = z.object({
  id: z.string(),
  name: z.string(),
  periods: z.array(z.object({
    from_day: z.enum(WEEKDAYS),
    to_day: z.enum(WEEKDAYS),
    begin: z.string(),
    end: z.string(),
  })),
});
export type SimCalendar = z.infer<typeof simCalendarSchema>;

export const scenarioTemplateSchema = z.object({
  resources: z.array(scenarioTemplateResourceSchema).optional(),
  /** Il calendario di arrivi e risorse senza calendario proprio. */
  standard_calendar: simCalendarSchema.nullable().optional(),
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
 * The Simulation IR's five-level provenance (SIM-07), as the API sends it.
 * Mirrors `Provenance` in `backend/simulation/ir/model.py`: there is one
 * provenance in DeliR, and every screen reads this one (SIM-38).
 */
export const provenanceOriginSchema = z.enum([
  "observed",
  "inferred",
  "declared",
  "estimated",
  "manual",
]);
export type ProvenanceOrigin = z.infer<typeof provenanceOriginSchema>;

export const parameterSourceRefSchema = z.object({
  kind: z.enum(["claim", "source", "event_log", "document", "interview", "user"]),
  id: z.string(),
  label: z.string().nullable().optional(),
});
export type ParameterSourceRef = z.infer<typeof parameterSourceRefSchema>;

export const parameterProvenanceSchema = z.object({
  origin: provenanceOriginSchema,
  confidence: z.enum(["high", "medium", "low"]).nullable().optional(),
  sources: z.array(parameterSourceRefSchema).default([]),
  note: z.string().nullable().optional(),
});
export type ParameterProvenance = z.infer<typeof parameterProvenanceSchema>;

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
      provenance: parameterProvenanceSchema,
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
  /** Assente = il calendario standard. */
  calendarId?: string;
};

export type SimDurationInput = {
  meanSeconds: number;
  distribution: DistributionName;
  /** Assenti = le assunzioni del backend (dev. std al 10%, limiti a ±3σ). */
  stdSeconds?: number;
  minSeconds?: number;
  maxSeconds?: number;
};

/** Gli arrivi (A2-3): il tempo fra due arrivi e il calendario in cui arrivano. */
export type SimArrivalInput = SimDurationInput & { calendarId?: string };

/** SIM-07: le affermazioni dei file proposte come fonte di ogni attivita'. */
export const claimProposalSchema = z.object({
  claim_id: z.number(),
  statement: z.string(),
  quote: z.string(),
  quote_verified: z.boolean(),
  source_id: z.string(),
  source_name: z.string(),
  score: z.number(),
  duration_hint: z.object({ text: z.string(), seconds: z.number() }).nullable().optional(),
});
export type ClaimProposal = z.infer<typeof claimProposalSchema>;

export const simulationClaimsSchema = z.object({
  sources: z.number(),
  activities: z.array(z.object({ element_id: z.string(), name: z.string(), proposals: z.array(claimProposalSchema) })),
});
export type SimulationClaims = z.infer<typeof simulationClaimsSchema>;

export type SimTaskInput = SimDurationInput & {
  elementId: string;
  resourceId: string | null;
  /** Le affermazioni confermate dal consulente come fonte della durata. */
  claims?: { claimId: number; label: string }[];
  /** SIM-10: euro per esecuzione. */
  fixedCost?: number;
  /** SIM-32: durate per categoria di un attributo del caso. */
  durationBy?: { attribute: string; variants: (SimDurationInput & { value: string })[] };
  /** Gli altri ruoli che possono svolgere l'attività, ognuno con la sua durata. */
  otherAssignments?: (SimDurationInput & { resourceId: string })[];
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
  arrival?: SimArrivalInput;
  /** SIM-13: obiettivo di servizio, in secondi e quota 0-1. */
  sla?: { targetSeconds: number; share: number };
  /** SIM-10: euro per caso completato. */
  caseFixedCost?: number;
  /** SIM-03: i primi casi fuori dai KPI. */
  warmupCases?: number;
  /** SIM-04: ripetizioni dello scenario. */
  replications?: number;
  resources?: SimResourceInput[];
  tasks?: SimTaskInput[];
  gateways?: SimGatewayInput[];
  calendars?: SimCalendar[];
  /** Cio' che i campi v1 non esprimono (attributi del caso, rami per regola), come patch dell'IR. */
  modelPatch?: ModelPatchInput;
  idempotencyKey?: string;
};
