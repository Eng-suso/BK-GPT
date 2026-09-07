import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";

import {
  apiArchiveImpactSchema,
  apiArchiveSchema,
  toClient,
  toProcess,
  toProject,
  type ArchiveImpact,
  type Client,
  type Project,
  type ProjectProcess,
} from "@/contracts/workspace";
import { http } from "@/lib/http";
import { clientKeys } from "@/features/clients/api";
import { projectKeys } from "@/features/projects/api";

/**
 * Il ciclo di vita dei record del workspace.
 *
 * Tre operazioni distinte, perche' sono tre decisioni distinte: archiviare
 * chiude un incarico e lo lascia leggibile, ripristinare lo riapre, eliminare
 * lo perde. Prima esisteva solo la creazione, e un cliente concluso restava
 * nell'elenco del lavoro corrente per sempre.
 */

export type RecordKind = "client" | "project" | "process";

const PATHS: Record<RecordKind, string> = {
  client: "clients",
  project: "projects",
  process: "processes",
};

export const archiveKeys = {
  all: ["workspace-archive"] as const,
  impact: (kind: RecordKind, id: string) =>
    ["workspace-impact", kind, id] as const,
};

export type WorkspaceArchive = {
  clients: Client[];
  projects: Project[];
  processes: ProjectProcess[];
};

/** Tutto cio' che e' stato chiuso. */
export function useArchiveQuery(): UseQueryResult<WorkspaceArchive> {
  return useQuery({
    queryKey: archiveKeys.all,
    queryFn: async () => {
      const raw = await http<unknown>("/v1/workspace/archive");
      const parsed = apiArchiveSchema.parse(raw);
      return {
        clients: parsed.clients.map(toClient),
        projects: parsed.projects.map(toProject),
        processes: parsed.processes.map(toProcess),
      };
    },
  });
}

/**
 * Cosa si porta dietro chiudere o eliminare questo record.
 *
 * Il numero lo conosce il database, non la UI: una conferma che dice "3
 * progetti e 5 processi" e' verificabile, "sei sicuro?" no.
 */
export function useRecordImpactQuery(
  kind: RecordKind,
  id: string | null,
): UseQueryResult<ArchiveImpact> {
  return useQuery({
    queryKey: archiveKeys.impact(kind, id ?? "none"),
    enabled: Boolean(id),
    queryFn: async () => {
      const raw = await http<unknown>(
        `/v1/workspace/${PATHS[kind]}/${id}/impact`,
      );
      return apiArchiveImpactSchema.parse(raw);
    },
  });
}

function useLifecycleInvalidation() {
  const queryClient = useQueryClient();
  return () => {
    // Chiudere un cliente muove progetti e processi: gli elenchi che li
    // mostrano vanno riletti tutti, non solo quello su cui si e' agito.
    void queryClient.invalidateQueries({ queryKey: clientKeys.all });
    void queryClient.invalidateQueries({ queryKey: projectKeys.all });
    void queryClient.invalidateQueries({ queryKey: archiveKeys.all });
  };
}

export type ArchiveInput = { kind: RecordKind; id: string; reason?: string };

/** Chiude un record e cio' che sta sotto di lui. */
export function useArchiveRecordMutation(): UseMutationResult<
  void,
  Error,
  ArchiveInput
> {
  const invalidate = useLifecycleInvalidation();
  return useMutation({
    mutationFn: async ({ kind, id, reason }) => {
      await http(`/v1/workspace/${PATHS[kind]}/${id}/archive`, {
        method: "POST",
        body: { reason: reason?.trim() || null },
      });
    },
    onSuccess: invalidate,
  });
}

/** Riapre un record chiuso. */
export function useRestoreRecordMutation(): UseMutationResult<
  void,
  Error,
  { kind: RecordKind; id: string }
> {
  const invalidate = useLifecycleInvalidation();
  return useMutation({
    mutationFn: async ({ kind, id }) => {
      await http(`/v1/workspace/${PATHS[kind]}/${id}/restore`, {
        method: "POST",
      });
    },
    onSuccess: invalidate,
  });
}

/** Elimina un record. Non si torna indietro. */
export function useDeleteRecordMutation(): UseMutationResult<
  ArchiveImpact,
  Error,
  { kind: RecordKind; id: string }
> {
  const invalidate = useLifecycleInvalidation();
  return useMutation({
    mutationFn: async ({ kind, id }) => {
      const raw = await http<unknown>(`/v1/workspace/${PATHS[kind]}/${id}`, {
        method: "DELETE",
        admin: true,
      });
      return apiArchiveImpactSchema.parse(raw);
    },
    onSuccess: invalidate,
  });
}
