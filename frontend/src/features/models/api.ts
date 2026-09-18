import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { z } from "zod";

import { ROUTES } from "@/app/routes";
import { http } from "@/lib/http";

/**
 * Backend seam for the model library. Components never call `fetch`; the page
 * reads through `useModelsQuery`.
 */

export const modelKeys = {
  all: ["workspace-models"] as const,
};

const apiModelSchema = z.object({
  bpmn_model_id: z.string(),
  name: z.string(),
  has_diagram: z.boolean(),
  version_count: z.number().int().nonnegative(),
  last_saved_at: z.string().nullable(),
  process_id: z.string(),
  process_name: z.string(),
  process_stage: z.string(),
  project_id: z.string(),
  project_name: z.string(),
  client_id: z.string(),
  client_name: z.string(),
  review_status: z.string().nullable(),
  review_version: z.number().int().nullable(),
  readiness_score: z.number().nullable(),
  review_updated_at: z.string().nullable(),
  conformance_verdict: z.string().nullable(),
  conformance_findings: z.number().int().nonnegative(),
  conformance_pending: z.boolean(),
});

export type ApiModel = z.infer<typeof apiModelSchema>;

/** Where a model stands, in the order the work moves it forward. */
export type ModelStage = "toDraw" | "noPlan" | "inReview" | "toFix" | "approved";

export type ModelLibraryItem = {
  id: string;
  name: string;
  hasDiagram: boolean;
  versionCount: number;
  processId: string;
  processName: string;
  projectId: string;
  projectName: string;
  clientName: string;
  reviewStatus: string | null;
  readiness: number | null;
  conformanceVerdict: string | null;
  conformanceFindings: number;
  conformancePending: boolean;
  /** The most recent of last save and last review change; `null` when never touched. */
  touchedAt: string | null;
  stage: ModelStage;
};

/**
 * One stage per model, so the list can be filtered on the question the
 * consultant is actually asking: what do I have to do on this one?
 */
export function modelStage(model: ApiModel): ModelStage {
  if (!model.has_diagram) return "toDraw";
  if (model.review_status === "approved") return "approved";
  if (model.conformance_verdict === "not_conformant") return "toFix";
  if (model.review_status == null) return "noPlan";
  return "inReview";
}

function toModel(model: ApiModel): ModelLibraryItem {
  const touched = [model.last_saved_at, model.review_updated_at]
    .filter((value): value is string => Boolean(value))
    .sort()
    .at(-1);
  return {
    id: model.bpmn_model_id,
    name: model.name,
    hasDiagram: model.has_diagram,
    versionCount: model.version_count,
    processId: model.process_id,
    processName: model.process_name,
    projectId: model.project_id,
    projectName: model.project_name,
    clientName: model.client_name,
    reviewStatus: model.review_status,
    readiness: model.readiness_score,
    conformanceVerdict: model.conformance_verdict,
    conformanceFindings: model.conformance_findings,
    conformancePending: model.conformance_pending,
    touchedAt: touched ?? null,
    stage: modelStage(model),
  };
}

/** Dove si apre un modello: sul disegno se c'e', altrimenti sul processo, da cui si disegna. */
export function modelHref(model: ModelLibraryItem): string {
  const process = ROUTES.projects.process(model.projectId, model.processId);
  return model.hasDiagram ? `${process}?view=canvas` : process;
}

/** Every BPMN model of the active processes, most recently touched first. */
export async function fetchModels(): Promise<ModelLibraryItem[]> {
  const data = await http<unknown>("/v1/workspace/models");
  return z.array(apiModelSchema).parse(data).map(toModel);
}

export function useModelsQuery(): UseQueryResult<ModelLibraryItem[]> {
  return useQuery({ queryKey: modelKeys.all, queryFn: fetchModels });
}
