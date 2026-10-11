import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { http } from "@/lib/http";
import { toOwnerDashboard } from "./dashboardContract";

/**
 * Le chiamate dello studio: l'anteprima del cruscotto e il link del cliente.
 * Usano le credenziali dello studio, quindi la pagina del cliente non importa
 * mai questo file (lo verifica `shareIsolation.test.ts`).
 */
const keys = {
  preview: (processId: string) => ["workspace", "owner-dashboard", processId] as const,
  link: (processId: string) => ["workspace", "owner-link", processId] as const,
};

const linkStatusSchema = z.object({
  active: z.boolean(),
  created_at: z.string().nullable().optional(),
  expires_at: z.string().nullable().optional(),
  last_viewed_at: z.string().nullable().optional(),
  view_count: z.number().default(0),
});
const linkCreatedSchema = z.object({ token: z.string(), created_at: z.string(), expires_at: z.string() });

export type OwnerLinkStatus = z.infer<typeof linkStatusSchema>;
export type OwnerLinkCreated = z.infer<typeof linkCreatedSchema>;

/** L'anteprima: lo stesso cruscotto che il server manda al link del cliente. */
export function useOwnerDashboardPreview(processId: string) {
  return useQuery({
    queryKey: keys.preview(processId),
    queryFn: async () => toOwnerDashboard(await http<unknown>(`/v1/workspace/processes/${processId}/owner-dashboard`, { cache: "no-store" })),
  });
}

export function useOwnerLink(processId: string) {
  return useQuery({
    queryKey: keys.link(processId),
    queryFn: async () => linkStatusSchema.parse(await http<unknown>(`/v1/workspace/processes/${processId}/owner-link`, { cache: "no-store" })),
  });
}

export function useCreateOwnerLink(processId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async () => linkCreatedSchema.parse(await http<unknown>(`/v1/workspace/processes/${processId}/owner-link`, { method: "POST" })),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.link(processId) }),
  });
}

export function useRevokeOwnerLink(processId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async () => { await http<unknown>(`/v1/workspace/processes/${processId}/owner-link`, { method: "DELETE" }); },
    onSuccess: () => client.invalidateQueries({ queryKey: keys.link(processId) }),
  });
}

/** L'indirizzo che il consulente manda al cliente. Il codice sta dopo `#`: il browser non lo invia mai ai server. */
export function ownerLinkUrl(token: string, origin: string = window.location.origin): string {
  return `${origin}/share.html#${token}`;
}
