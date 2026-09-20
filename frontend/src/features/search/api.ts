import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { z } from "zod";

import { ROUTES } from "@/app/routes";
import { http } from "@/lib/http";

/**
 * Backend seam for the global search. Components never call `fetch`.
 */

export const searchKeys = {
  all: ["workspace-search"] as const,
  query: (query: string) => [...searchKeys.all, query] as const,
};

/** Sotto le due lettere una ricerca restituisce mezzo workspace: non e' una risposta. */
export const MIN_QUERY_LENGTH = 2;

const apiHitSchema = z.object({
  kind: z.enum(["client", "project", "process", "source"]),
  id: z.string(),
  title: z.string(),
  context: z.string(),
  client_id: z.string().nullable(),
  client_name: z.string().nullable(),
  project_id: z.string().nullable(),
  project_name: z.string().nullable(),
  process_id: z.string().nullable(),
  source_type: z.string().nullable(),
});

export type SearchHitKind = z.infer<typeof apiHitSchema>["kind"];

export type SearchHit = {
  kind: SearchHitKind;
  id: string;
  title: string;
  /** Dove vive, gia' scritto per chi legge. */
  context: string;
  clientName: string | null;
  projectId: string | null;
  processId: string | null;
  sourceType: string | null;
};

/**
 * Dove porta un risultato.
 *
 * Un cliente non ha una pagina propria in questo router: porta ai suoi
 * progetti, gia' filtrati, che e' il lavoro che si stava cercando. Una fonte
 * apre il progetto sulla scheda delle fonti, dove si legge.
 */
export function hitHref(hit: SearchHit): string {
  switch (hit.kind) {
    case "client":
      return `${ROUTES.projects.list}?f_client=${encodeURIComponent(hit.title)}`;
    case "project":
      return hit.projectId ? ROUTES.projects.detail(hit.projectId) : ROUTES.projects.list;
    case "process":
      return hit.projectId && hit.processId
        ? ROUTES.projects.process(hit.projectId, hit.processId)
        : ROUTES.projects.list;
    case "source":
      return hit.projectId
        ? `${ROUTES.projects.detail(hit.projectId)}?tab=sources`
        : ROUTES.projects.list;
  }
}

export async function searchWorkspace(query: string): Promise<SearchHit[]> {
  const params = new URLSearchParams({ q: query });
  const data = await http<unknown>(`/v1/workspace/search?${params}`);
  return z
    .array(apiHitSchema)
    .parse(data)
    .map((hit) => ({
      kind: hit.kind,
      id: hit.id,
      title: hit.title,
      context: hit.context,
      clientName: hit.client_name,
      projectId: hit.project_id,
      processId: hit.process_id,
      sourceType: hit.source_type,
    }));
}

export function useWorkspaceSearch(query: string, enabled: boolean): UseQueryResult<SearchHit[]> {
  return useQuery({
    queryKey: searchKeys.query(query),
    queryFn: () => searchWorkspace(query),
    enabled: enabled && query.length >= MIN_QUERY_LENGTH,
    staleTime: 30_000,
  });
}
