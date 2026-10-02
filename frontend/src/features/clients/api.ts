import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";

import {
  apiClientSchema,
  apiClientsSchema,
  toApiClientPayload,
  toClient,
  type Client,
  type ClientDraft,
} from "@/contracts/workspace";
import { http, httpList } from "@/lib/http";
import { projectKeys } from "@/features/projects/api";

export const clientKeys = {
  all: ["clients"] as const,
  list: () => [...clientKeys.all] as const,
};

/** Le righe arrivate e quante ne esistono: la lista ha un tetto (B12). */
export type ClientsPage = { rows: Client[]; total: number | null };

/**
 * Una sola richiesta, due viste: chi vuole solo l'elenco lo ottiene con
 * `select`, chi deve dire che l'elenco e' tagliato legge anche il conteggio.
 */
function clientsPageOptions() {
  return {
    queryKey: clientKeys.list(),
    queryFn: async (): Promise<ClientsPage> => {
      const page = await httpList<unknown>("/v1/workspace/clients");
      return { rows: apiClientsSchema.parse(page.rows).map(toClient), total: page.total };
    },
  };
}

/**
 * Fetches the workspace clients.
 *
 * @returns The query result containing the workspace clients
 */
export function useClientsQuery(): UseQueryResult<Client[]> {
  return useQuery({ ...clientsPageOptions(), select: (page: ClientsPage) => page.rows });
}

/** Come sopra, ma con il conteggio: serve a dire che l'elenco e' tagliato. */
export function useClientsPageQuery(): UseQueryResult<ClientsPage> {
  return useQuery(clientsPageOptions());
}

/**
 * Creates a client from a draft.
 *
 * @returns A mutation result whose successful value is the created client.
 */
export function useCreateClientMutation(): UseMutationResult<
  Client,
  Error,
  ClientDraft
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (draft: ClientDraft) => {
      const raw = await http<unknown>("/v1/workspace/clients", {
        method: "POST",
        body: toApiClientPayload(draft),
      });
      return toClient(apiClientSchema.parse(raw));
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: clientKeys.all });
    },
  });
}

/**
 * Provides a mutation for updating an existing client.
 *
 * Successful updates refresh client and project query data.
 *
 * @returns The client update mutation result
 */
export function useUpdateClientMutation(): UseMutationResult<
  Client,
  Error,
  { id: string; draft: ClientDraft }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, draft }) => {
      const raw = await http<unknown>(`/v1/workspace/clients/${id}`, {
        method: "PATCH",
        body: toApiClientPayload(draft),
      });
      return toClient(apiClientSchema.parse(raw));
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: clientKeys.all });
      // Il nome cliente compare anche nelle righe progetto.
      void queryClient.invalidateQueries({ queryKey: projectKeys.all });
    },
  });
}
