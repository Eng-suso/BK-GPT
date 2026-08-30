import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { apiClientsSchema, toClient, type Client } from "@/contracts/workspace";
import { http } from "@/lib/http";

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
