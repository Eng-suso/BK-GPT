import { http } from "@/lib/http";

import {
  experimentReportSchema,
  scenarioProvenanceSchema,
  scenarioTemplateSchema,
  simulationClaimsSchema,
  type SimulationClaims,
  simulationReplaySchema,
  simulationRunSchema,
  simulationRunsSchema,
  type CreateSimulationRunInput,
  type ExperimentReport,
  type ScenarioProvenance,
  type ScenarioTemplate,
  type SimulationReplay,
  type SimulationRun,
} from "./simulationTypes";

export async function runProsimosSimulation(
  bpmnModelId: string,
  input: CreateSimulationRunInput,
): Promise<SimulationRun> {
  const raw = await http<unknown>(
    `/v1/workspace/bpmn-models/${bpmnModelId}/simulation-runs`,
    {
      method: "POST",
      body: {
        scenario_name: input.scenarioName,
        total_cases: input.totalCases,
        current_bpmn_xml: input.currentBpmnXml,
        arrival_interval_seconds: input.arrivalIntervalSeconds,
        default_task_duration_seconds: input.defaultTaskDurationSeconds,
        default_cost_per_hour: input.defaultCostPerHour,
        resource_amount: input.resourceAmount,
        resource_name: input.resourceName,
        sla: input.sla && { target_seconds: input.sla.targetSeconds, share: input.sla.share },
        case_fixed_cost: input.caseFixedCost,
        arrival: input.arrival && {
          mean_seconds: input.arrival.meanSeconds,
          distribution: input.arrival.distribution,
          std_seconds: input.arrival.stdSeconds,
          min_seconds: input.arrival.minSeconds,
          max_seconds: input.arrival.maxSeconds,
          calendar_id: input.arrival.calendarId,
        },
        resources: input.resources?.map((r) => ({
          id: r.id,
          name: r.name,
          cost_per_hour: r.costPerHour,
          amount: r.amount,
          calendar_id: r.calendarId,
        })),
        tasks: input.tasks?.map((task) => ({
          element_id: task.elementId,
          mean_seconds: task.meanSeconds,
          distribution: task.distribution,
          resource_id: task.resourceId,
          std_seconds: task.stdSeconds,
          min_seconds: task.minSeconds,
          max_seconds: task.maxSeconds,
          claims: task.claims?.map((claim) => ({ claim_id: claim.claimId, label: claim.label })),
          fixed_cost: task.fixedCost,
          duration_by: task.durationBy && {
            attribute: task.durationBy.attribute,
            variants: task.durationBy.variants.map((v) => ({
              value: v.value,
              mean_seconds: v.meanSeconds,
              distribution: v.distribution,
              std_seconds: v.stdSeconds,
              min_seconds: v.minSeconds,
              max_seconds: v.maxSeconds,
            })),
          },
          other_assignments: task.otherAssignments?.map((other) => ({
            resource_id: other.resourceId,
            mean_seconds: other.meanSeconds,
            distribution: other.distribution,
            std_seconds: other.stdSeconds,
            min_seconds: other.minSeconds,
            max_seconds: other.maxSeconds,
          })),
        })),
        gateways: input.gateways?.map((g) => ({
          element_id: g.elementId,
          branches: g.branches.map((b) => ({
            flow_id: b.flowId,
            probability: b.probability,
          })),
        })),
        calendars: input.calendars?.length ? input.calendars : undefined,
        model_patch: input.modelPatch,
        idempotency_key: input.idempotencyKey,
      },
    },
  );

  return simulationRunSchema.parse(raw);
}

export async function fetchScenarioTemplate(
  bpmnModelId: string,
  currentBpmnXml: string | null,
): Promise<ScenarioTemplate> {
  const raw = await http<unknown>(
    `/v1/workspace/bpmn-models/${bpmnModelId}/simulation-template`,
    { method: "POST", body: { current_bpmn_xml: currentBpmnXml } },
  );

  return scenarioTemplateSchema.parse(raw);
}

/** SIM-07: le affermazioni dei file che nominano ogni attivita'. */
export async function fetchSimulationClaims(bpmnModelId: string, currentBpmnXml: string | null): Promise<SimulationClaims> {
  const raw = await http<unknown>(`/v1/workspace/bpmn-models/${bpmnModelId}/simulation-claims`, {
    method: "POST",
    body: { current_bpmn_xml: currentBpmnXml },
  });
  return simulationClaimsSchema.parse(raw);
}

/** Where each simulable element came from — discovery evidence or inference. */
export async function fetchScenarioProvenance(
  bpmnModelId: string,
  currentBpmnXml: string | null,
): Promise<ScenarioProvenance> {
  const raw = await http<unknown>(
    `/v1/workspace/bpmn-models/${bpmnModelId}/simulation-provenance`,
    { method: "POST", body: { current_bpmn_xml: currentBpmnXml } },
  );

  return scenarioProvenanceSchema.parse(raw);
}

export async function listProsimosSimulationRuns(
  bpmnModelId: string,
): Promise<SimulationRun[]> {
  const raw = await http<unknown>(
    `/v1/workspace/bpmn-models/${bpmnModelId}/simulation-runs`,
  );

  return simulationRunsSchema.parse(raw);
}

export async function getProsimosSimulationRun(
  runId: number,
): Promise<SimulationRun> {
  const raw = await http<unknown>(`/v1/workspace/simulation-runs/${runId}`);

  return simulationRunSchema.parse(raw);
}

/** Heuristic "what should I try next" for a completed run (Phase 9). */
export async function fetchSimulationExperiments(
  runId: number,
): Promise<ExperimentReport> {
  const raw = await http<unknown>(
    `/v1/workspace/simulation-runs/${runId}/experiments`,
  );
  return experimentReportSchema.parse(raw);
}

/** The heavy replay artifact — only the replay / dashboard screens need it. */
export async function getSimulationReplay(
  runId: number,
): Promise<SimulationReplay> {
  const raw = await http<unknown>(
    `/v1/workspace/simulation-runs/${runId}/replay`,
  );

  return simulationReplaySchema.parse(raw);
}
