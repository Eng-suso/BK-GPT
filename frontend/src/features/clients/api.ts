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
import { http } from "@/lib/http";
import { projectKeys } from "@/features/projects/api";

export const clientKeys = {
  all: ["clients"] as const,
  list: () => [...clientKeys.all] as const,
};

export function useClientsQuery(): UseQueryResult<Client[]> {
  return useQuery({
    queryKey: clientKeys.list(),
    queryFn: async () => {
      const raw = await http<unknown>("/v1/workspace/clients");
      return apiClientsSchema.parse(raw).map(toClient);
    },
  });
}

/**
 * Crea un cliente a mano. Il record e' lo stesso che scrive l'agente: qui il
 * consulente non passa dalla chat, ma finisce nella stessa anagrafica.
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

/** Modifica manuale: correggere un campo gia' deciso e' un update, non una create. */
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
