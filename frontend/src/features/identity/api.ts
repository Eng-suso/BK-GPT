import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { z } from "zod";

import { http } from "@/lib/http";

/**
 * Backend seam for who is using the product — as far as the backend really knows.
 */

export const identityKeys = {
  current: ["identity", "me"] as const,
};

const apiIdentitySchema = z.object({
  tenant_id: z.string(),
  auth_mode: z.string(),
  auth_enabled: z.boolean(),
  is_admin: z.boolean(),
  caller_id: z.string(),
  has_user_identity: z.boolean(),
});

export type Identity = {
  /** Lo spazio di lavoro a cui le richieste sono associate. */
  tenantId: string;
  /** `local` (nessuna autenticazione) o `bearer` (token condiviso). */
  authMode: string;
  authEnabled: boolean;
  isAdmin: boolean;
  callerId: string;
  /** Falso finche' non esiste l'identita' per persona (Track B). */
  hasUserIdentity: boolean;
};

export async function fetchIdentity(): Promise<Identity> {
  const data = await http<unknown>("/v1/auth/me");
  const parsed = apiIdentitySchema.parse(data);
  return {
    tenantId: parsed.tenant_id,
    authMode: parsed.auth_mode,
    authEnabled: parsed.auth_enabled,
    isAdmin: parsed.is_admin,
    callerId: parsed.caller_id,
    hasUserIdentity: parsed.has_user_identity,
  };
}

export function useIdentityQuery(): UseQueryResult<Identity> {
  return useQuery({
    queryKey: identityKeys.current,
    queryFn: fetchIdentity,
    // Cambia solo con la configurazione dell'ambiente: non vale un giro di rete
    // per schermata.
    staleTime: 5 * 60_000,
    retry: false,
  });
}

/**
 * Come si chiama lo spazio di lavoro per chi legge.
 *
 * Finche' non c'e' un'anagrafica di organizzazioni, il nome e' l'identificativo
 * dell'ambiente: dire "Gruppo DeliR" a un cliente che si chiama diversamente e'
 * peggio che dire `local`.
 */
export function workspaceLabel(identity: Identity | undefined): string | null {
  return identity?.tenantId ?? null;
}
