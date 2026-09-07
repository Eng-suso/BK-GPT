import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";

import {
  toApiProcessPayload,
  toApiProjectPayload,
  toProcess,
  apiProcessSchema,
  type ProcessDraft,
  type ProjectDraft,
  type ProjectProcess,
  apiProjectSchema,
  apiProjectsSchema,
  apiProjectSourcesSchema,
  apiProjectDecisionsSchema,
  toProject,
  toProjectSource,
  toProjectDecision,
  type ProjectSource,
  type ProjectDecision,
} from "@/contracts/workspace";
import { http } from "@/lib/http";
import type { Project } from "./types";

export const projectKeys = {
  all: ["projects"] as const,
  list: () => [...projectKeys.all] as const,
  detail: (id: string) => [...projectKeys.all, id] as const,
  sources: (id: string) => [...projectKeys.all, id, "sources"] as const,
  decisions: (id: string) => [...projectKeys.all, id, "decisions"] as const,
};

export function useProjectsQuery(): UseQueryResult<Project[]> {
  return useQuery({
    queryKey: projectKeys.list(),
    queryFn: async () => {
      const raw = await http<unknown>("/v1/workspace/projects");
      return apiProjectsSchema.parse(raw).map(toProject);
    },
  });
}

export function useProjectQuery(id: string): UseQueryResult<Project> {
  return useQuery({
    queryKey: projectKeys.detail(id),
    queryFn: async () => {
      const raw = await http<unknown>(`/v1/workspace/projects/${id}`);
      return toProject(apiProjectSchema.parse(raw));
    },
  });
}

/**
 * Crea un progetto a mano. `objective` viaggia con la create: e' il perche'
 * dell'incarico, e senza di lui il record nasce senza mandato (PROJECT-01).
 */
export function useCreateProjectMutation(): UseMutationResult<
  Project,
  Error,
  ProjectDraft
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (draft: ProjectDraft) => {
      const raw = await http<unknown>("/v1/workspace/projects", {
        method: "POST",
        body: toApiProjectPayload(draft),
      });
      return toProject(apiProjectSchema.parse(raw));
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: projectKeys.all });
      // Il conteggio progetti vive sulla riga cliente.
      void queryClient.invalidateQueries({ queryKey: ["clients"] });
    },
  });
}

/** Modifica manuale del progetto: obiettivo, fase, stato, avanzamento, liste. */
export function useUpdateProjectMutation(): UseMutationResult<
  Project,
  Error,
  { id: string; draft: ProjectDraft }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, draft }) => {
      const raw = await http<unknown>(`/v1/workspace/projects/${id}`, {
        method: "PATCH",
        body: toApiProjectPayload(draft),
      });
      return toProject(apiProjectSchema.parse(raw));
    },
    onSuccess: (project) => {
      queryClient.setQueryData(projectKeys.detail(project.id), project);
      void queryClient.invalidateQueries({ queryKey: projectKeys.all });
      void queryClient.invalidateQueries({ queryKey: ["clients"] });
    },
  });
}

/** Registra un processo nel progetto: record + modello BPMN vuoto. */
export function useCreateProcessMutation(
  projectId: string,
): UseMutationResult<ProjectProcess, Error, ProcessDraft> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (draft: ProcessDraft) => {
      const raw = await http<unknown>(
        `/v1/workspace/projects/${projectId}/processes`,
        { method: "POST", body: toApiProcessPayload(draft) },
      );
      return toProcess(apiProcessSchema.parse(raw));
    },
    onSuccess: () => {
      // Il progetto porta i suoi processi e il loro conteggio.
      void queryClient.invalidateQueries({ queryKey: projectKeys.all });
    },
  });
}

/** Modifica manuale del processo: nome, stadio, stato, owner, readiness. */
export function useUpdateProcessMutation(): UseMutationResult<
  ProjectProcess,
  Error,
  { id: string; draft: ProcessDraft }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, draft }) => {
      const raw = await http<unknown>(`/v1/workspace/processes/${id}`, {
        method: "PATCH",
        body: toApiProcessPayload(draft),
      });
      return toProcess(apiProcessSchema.parse(raw));
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: projectKeys.all });
    },
  });
}

export function useProjectSourcesQuery(
  id: string,
): UseQueryResult<ProjectSource[]> {
  return useQuery({
    queryKey: projectKeys.sources(id),
    queryFn: async () => {
      const raw = await http<unknown>(`/v1/workspace/projects/${id}/sources`);
      return apiProjectSourcesSchema.parse(raw).map(toProjectSource);
    },
  });
}

export function useProjectDecisionsQuery(
  id: string,
): UseQueryResult<ProjectDecision[]> {
  return useQuery({
    queryKey: projectKeys.decisions(id),
    queryFn: async () => {
      const raw = await http<unknown>(`/v1/workspace/projects/${id}/decisions`);
      return apiProjectDecisionsSchema.parse(raw).map(toProjectDecision);
    },
  });
}
