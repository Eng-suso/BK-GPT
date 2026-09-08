import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";

import {
  toApiMilestonePayload,
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
  type Milestone,
  toProject,
  toProjectSource,
  toProjectDecision,
  toSourceDocument,
  apiSourceDocumentSchema,
  type SourceDocument,
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
  sourceDocument: (sourceId: string) =>
    [...projectKeys.all, "source", sourceId, "document"] as const,
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

/**
 * Fetches a project by ID.
 *
 * @param id - The project identifier
 * @returns The project query result
 */
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
 * Creates a project from a project draft.
 *
 * @param draft - The project details to submit
 * @returns The created project
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

/**
 * Provides a mutation for updating an existing project from a draft.
 *
 * @returns The mutation result for updating a project.
 */
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

/**
 * Writes the project's milestone list with the state of each entry.
 *
 * Separate from `useUpdateProjectMutation`, which carries a whole draft: marking
 * a milestone reached touches one field and must not resend the rest of the
 * record from a view that may be a few seconds stale.
 *
 * @param projectId - The project whose milestones are written
 * @returns The mutation writing the milestone list
 */
export function useSetProjectMilestonesMutation(
  projectId: string,
): UseMutationResult<Project, Error, Milestone[]> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (milestones: Milestone[]) => {
      const raw = await http<unknown>(`/v1/workspace/projects/${projectId}`, {
        method: "PATCH",
        body: { milestones: toApiMilestonePayload(milestones) },
      });
      return toProject(apiProjectSchema.parse(raw));
    },
    onSuccess: (project) => {
      queryClient.setQueryData(projectKeys.detail(project.id), project);
      void queryClient.invalidateQueries({ queryKey: projectKeys.all });
    },
  });
}

/**
 * Creates a process within a project.
 *
 * @param projectId - The ID of the project that will contain the process
 * @returns The created project process
 */
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

/**
 * Updates an existing project process from a draft.
 *
 * @param id - The process identifier and update payload.
 * @param draft - The process fields to update.
 * @returns The updated project process.
 */
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

/**
 * Fetches the sources associated with a project.
 *
 * @param id - The project identifier
 * @returns The project's sources
 */
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

/**
 * Fetches one source with its summary and its full text.
 *
 * Only runs when a source is actually open: a transcript is not something to
 * prefetch for every row of the list.
 *
 * @param sourceId - The source to read, or null when none is open
 * @returns The source document
 */
export function useSourceDocumentQuery(
  sourceId: string | null,
): UseQueryResult<SourceDocument> {
  return useQuery({
    queryKey: projectKeys.sourceDocument(sourceId ?? ""),
    enabled: sourceId !== null,
    queryFn: async () => {
      const raw = await http<unknown>(
        `/v1/workspace/sources/${sourceId}/document`,
      );
      return toSourceDocument(apiSourceDocumentSchema.parse(raw));
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
