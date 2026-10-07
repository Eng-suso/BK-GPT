import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
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
  apiProjectSourceSchema,
  apiSourceClaimsSchema,
  apiClaimRelationsSchema,
  toClaimRelations,
  type ClaimRelation,
  toSourceClaims,
  apiUploadedSourceSchema,
  apiProjectDecisionsSchema,
  type Milestone,
  toProject,
  toProjectSource,
  toProjectDecision,
  toSourceDocument,
  apiSourceDocumentSchema,
  type SourceDocument,
  type ProjectSource,
  type SourceClaim,
  type SourceRole,
  type SourceUpload,
  type ProjectDecision,
} from "@/contracts/workspace";
import { http, httpBlob, httpList } from "@/lib/http";
import type { Project } from "./types";

export const projectKeys = {
  all: ["projects"] as const,
  list: () => [...projectKeys.all] as const,
  detail: (id: string) => [...projectKeys.all, id] as const,
  sources: (id: string) => [...projectKeys.all, id, "sources"] as const,
  sourceClaims: (sourceId: string) => [...projectKeys.all, "source", sourceId, "claims"] as const,
  sourceRelations: (sourceId: string) => [...projectKeys.all, "source", sourceId, "relations"] as const,
  sourceDocument: (sourceId: string) =>
    [...projectKeys.all, "source", sourceId, "document"] as const,
  decisions: (id: string) => [...projectKeys.all, id, "decisions"] as const,
};

/** Le righe arrivate e quante ne esistono: la lista ha un tetto (B12). */
export type ProjectsPage = { rows: Project[]; total: number | null };

/**
 * Una sola richiesta, due viste: chi vuole solo l'elenco lo ottiene con
 * `select`, chi deve dire che l'elenco e' tagliato legge anche il conteggio.
 */
function projectsPageOptions() {
  return {
    queryKey: projectKeys.list(),
    queryFn: async (): Promise<ProjectsPage> => {
      const page = await httpList<unknown>("/v1/workspace/projects");
      return { rows: apiProjectsSchema.parse(page.rows).map(toProject), total: page.total };
    },
  };
}

export function useProjectsQuery(): UseQueryResult<Project[]> {
  return useQuery({ ...projectsPageOptions(), select: (page: ProjectsPage) => page.rows });
}

/** Come sopra, ma con il conteggio: serve a dire che l'elenco e' tagliato. */
export function useProjectsPageQuery(): UseQueryResult<ProjectsPage> {
  return useQuery(projectsPageOptions());
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
  options: { enabled?: boolean } = {},
): UseQueryResult<ProjectSource[]> {
  return useQuery({
    queryKey: projectKeys.sources(id),
    enabled: options.enabled ?? true,
    queryFn: async () => {
      const raw = await http<unknown>(`/v1/workspace/projects/${id}/sources`);
      return apiProjectSourcesSchema.parse(raw).map(toProjectSource);
    },
    // Un file caricato viene letto dal worker dopo la risposta: finche' una
    // fonte e' in lettura la lista si aggiorna da sola, poi smette.
    // Anche mentre DeliR estrae le affermazioni: il dettaglio della fonte le
    // mostra appena ci sono.
    refetchInterval: (query) =>
      query.state.data?.some(
        (source) =>
          source.acquisitionStatus === "pending" ||
          source.claimsStatus === "pending" ||
          source.reconcileStatus === "pending",
      )
        ? 1500
        : false,
  });
}

export type UploadedSource = ProjectSource & {
  /** `false`: lo stesso file c'era gia' tra le Fonti. */
  created: boolean;
  /** I ruoli che il nome e il formato suggeriscono; `null` se non dicono niente. */
  suggestedRoles: SourceRole[] | null;
};

export function useUploadProjectSourceMutation(
  projectId: string,
): UseMutationResult<UploadedSource, Error, SourceUpload> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ file, roles, retention, scopes }) => {
      const body = sourceUploadForm({ file, roles, retention, scopes });
      const raw = await http<unknown>(
        `/v1/workspace/projects/${projectId}/sources/upload`,
        { method: "POST", body },
      );
      const parsed = apiUploadedSourceSchema.parse(raw);
      return {
        ...toProjectSource(parsed),
        created: parsed.created,
        suggestedRoles: parsed.suggested_roles,
      };
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: projectKeys.sources(projectId) });
      void queryClient.invalidateQueries({ queryKey: projectKeys.detail(projectId) });
    },
  });
}

/**
 * Conferma un file caricato come evidenza del processo.
 *
 * Il testo estratto da un parser non e' ancora una fonte che il consulente ha
 * fatto propria: entra nel registro dell'evidenza solo da qui.
 */
export function useVerifyProjectSourceMutation(
  projectId: string,
): UseMutationResult<ProjectSource, Error, string> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (sourceId) => {
      const raw = await http<unknown>(`/v1/workspace/sources/${sourceId}/verify`, {
        method: "POST",
      });
      return toProjectSource(apiProjectSourceSchema.parse(raw));
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: projectKeys.sources(projectId) });
    },
  });
}

/**
 * Carica un file per tutto il cliente (P1.16): appartiene al cliente e compare
 * nelle Fonti di ogni suo progetto. Per questo si rileggono le Fonti di tutti
 * i progetti in cache, non solo quelle del progetto aperto.
 */
export function useUploadClientSourceMutation(
  clientId: string,
): UseMutationResult<UploadedSource, Error, Omit<SourceUpload, "scopes">> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ file, roles, retention }) => {
      const body = sourceUploadForm({ file, roles, retention, scopes: [] });
      const raw = await http<unknown>(`/v1/workspace/clients/${clientId}/sources/upload`, {
        method: "POST",
        body,
      });
      const parsed = apiUploadedSourceSchema.parse(raw);
      return {
        ...toProjectSource(parsed),
        created: parsed.created,
        suggestedRoles: parsed.suggested_roles,
      };
    },
    onSuccess: () => invalidateEverySourcesList(queryClient),
  });
}

/** Rilegge le Fonti di ogni progetto in cache: una fonte del cliente sta in tutte. */
export function invalidateEverySourcesList(queryClient: QueryClient): void {
  void queryClient.invalidateQueries({
    predicate: (query) =>
      query.queryKey[0] === projectKeys.all[0] && query.queryKey.at(-1) === "sources",
  });
}

export function sourceUploadForm({ file, roles, retention, scopes }: SourceUpload): FormData {
  const body = new FormData();
  body.append("file", file);
  body.append("roles", JSON.stringify(roles));
  body.append("retention", retention);
  body.append("scopes", JSON.stringify(scopes));
  return body;
}

/**
 * Scarta un file caricato e non ancora confermato come evidenza.
 *
 * E' la regola della card del composer: un file nuovo tolto prima dell'invio
 * non resta tra le Fonti.
 */
/** Cambia a cosa serve una fonte: la stessa fonte, un altro attributo. */
export async function updateSourceRoles(sourceId: string, roles: SourceRole[]): Promise<ProjectSource> {
  const raw = await http<unknown>(`/v1/workspace/sources/${sourceId}`, {
    method: "PATCH",
    body: { roles },
  });
  return toProjectSource(apiProjectSourceSchema.parse(raw));
}

export async function discardSource(sourceId: string): Promise<void> {
  await http<unknown>(`/v1/workspace/sources/${sourceId}`, { method: "DELETE" });
}

export function downloadSourceOriginal(sourceId: string): Promise<Blob> {
  return httpBlob(`/v1/workspace/sources/${sourceId}/original`);
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
  acquisitionStatus: string | null = null,
): UseQueryResult<SourceDocument> {
  return useQuery({
    // Lo stato fa parte della chiave: quando la lettura finisce, il testo
    // aperto si ricarica invece di restare quello vuoto di prima.
    queryKey: [...projectKeys.sourceDocument(sourceId ?? ""), acquisitionStatus],
    enabled: sourceId !== null,
    queryFn: async () => {
      const raw = await http<unknown>(
        `/v1/workspace/sources/${sourceId}/document`,
      );
      return toSourceDocument(apiSourceDocumentSchema.parse(raw));
    },
  });
}

/**
 * Le affermazioni di una fonte, quando l'estrazione e' finita.
 *
 * Lo stato fa parte della chiave: quando l'estrazione passa a `done` la lista
 * si ricarica invece di restare quella vuota di prima.
 */
export function useSourceClaimsQuery(
  sourceId: string | null,
  claimsStatus: string | null,
): UseQueryResult<SourceClaim[]> {
  return useQuery({
    queryKey: [...projectKeys.sourceClaims(sourceId ?? ""), claimsStatus],
    enabled: sourceId !== null && claimsStatus === "done",
    queryFn: async () => {
      const raw = await http<unknown>(`/v1/workspace/sources/${sourceId}/claims`);
      return toSourceClaims(apiSourceClaimsSchema.parse(raw));
    },
  });
}

/**
 * Le affermazioni di una fonte che altri file confermano o contraddicono.
 *
 * Una relazione puo' nascere anche dal confronto di un altro file, arrivato
 * dopo: per questo la lista si rilegge ogni volta che il dettaglio si apre.
 */
export function useSourceRelationsQuery(
  sourceId: string | null,
  reconcileStatus: string | null,
): UseQueryResult<ClaimRelation[]> {
  return useQuery({
    queryKey: [...projectKeys.sourceRelations(sourceId ?? ""), reconcileStatus],
    enabled: sourceId !== null && (reconcileStatus === "done" || reconcileStatus === "failed"),
    staleTime: 0,
    refetchOnMount: "always",
    queryFn: async () => {
      const raw = await http<unknown>(`/v1/workspace/sources/${sourceId}/relations`);
      return toClaimRelations(apiClaimRelationsSchema.parse(raw));
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
