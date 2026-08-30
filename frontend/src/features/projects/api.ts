import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import {
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
