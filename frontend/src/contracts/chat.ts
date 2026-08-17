import { z } from "zod";

export const apiChatScopeSchema = z.discriminatedUnion("type", [
  z.object({ type: z.literal("consultant") }),
  z.object({
    type: z.literal("project"),
    project_id: z.string().min(1),
  }),
  z.object({
    type: z.literal("process"),
    project_id: z.string().min(1),
    process_id: z.string().min(1),
  }),
  z.object({
    type: z.literal("canvas"),
    project_id: z.string().min(1),
    process_id: z.string().min(1),
    bpmn_model_id: z.string().min(1),
    current_bpmn_xml: z.string().nullable().optional(),
  }),
]);

export type ApiChatScope = z.infer<typeof apiChatScopeSchema>;

export type ChatScope =
  | { type: "consultant" }
  | { type: "project"; projectId: string; projectName: string }
  | { type: "process"; projectId: string; processId: string; processName: string }
  | {
      type: "canvas";
      projectId: string;
      processId: string;
      processName: string;
      bpmnModelId: string;
      currentBpmnXml?: string | null;
    };

export function toApiChatScope(
  scope: ChatScope,
  options: { includeTransient?: boolean } = {},
): ApiChatScope {
  const includeTransient = options.includeTransient ?? true;
  const apiScope =
    scope.type === "project"
      ? { type: scope.type, project_id: scope.projectId }
      : scope.type === "process"
        ? { type: scope.type, project_id: scope.projectId, process_id: scope.processId }
        : scope.type === "canvas"
          ? {
              type: scope.type,
              project_id: scope.projectId,
              process_id: scope.processId,
              bpmn_model_id: scope.bpmnModelId,
              ...(includeTransient && scope.currentBpmnXml
                ? { current_bpmn_xml: scope.currentBpmnXml }
                : {}),
            }
          : { type: "consultant" };

  return apiChatScopeSchema.parse(apiScope);
}

export function chatScopeKey(scope: ApiChatScope): string {
  if (scope.type === "consultant") return "consultant";
  if (scope.type === "project") return `project:${scope.project_id}`;
  if (scope.type === "process") return `process:${scope.project_id}:${scope.process_id}`;
  return `canvas:${scope.project_id}:${scope.process_id}:${scope.bpmn_model_id}`;
}
