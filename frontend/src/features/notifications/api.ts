import { useMutation, useQuery, useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import { z } from "zod";

import { ROUTES } from "@/app/routes";
import { http } from "@/lib/http";

/**
 * Backend seam for the notifications bell. Components never call `fetch`.
 */

export const notificationKeys = {
  all: ["workspace-notifications"] as const,
};

const apiNotificationSchema = z.object({
  id: z.string(),
  kind: z.enum([
    "plan_ready",
    "plan_failed",
    "conformance_findings",
    "simulation_done",
    "simulation_failed",
  ]),
  occurred_at: z.string(),
  read: z.boolean(),
  process_id: z.string(),
  process_name: z.string(),
  project_id: z.string(),
  project_name: z.string(),
  client_name: z.string(),
  bpmn_model_id: z.string().nullable(),
  count: z.number().int().nonnegative(),
  version: z.number().int().nullable(),
  detail: z.string(),
  run_id: z.number().int().nullable(),
});

const apiResponseSchema = z.object({
  items: z.array(apiNotificationSchema),
  unread: z.number().int().nonnegative(),
});

export type NotificationKind = z.infer<typeof apiNotificationSchema>["kind"];

export type Notification = {
  id: string;
  kind: NotificationKind;
  occurredAt: string;
  read: boolean;
  processId: string;
  processName: string;
  projectId: string;
  projectName: string;
  clientName: string;
  /** Quanti rilievi ha trovato il confronto con le fonti. */
  count: number;
  /** La versione del piano appena ricostruito. */
  version: number | null;
  /** Il perche' di un guasto, o il nome dello scenario simulato. */
  detail: string;
  runId: number | null;
};

export type NotificationFeed = {
  items: Notification[];
  unread: number;
};

/** Gli avvisi che portano a un guasto: il consulente deve poterli distinguere a colpo d'occhio. */
export const FAILURE_KINDS: NotificationKind[] = ["plan_failed", "simulation_failed"];

/**
 * Dove porta un avviso: sul posto in cui la cosa si guarda o si ripara.
 *
 * Un confronto con rilievi si legge sul disegno; una simulazione finita nella
 * sua sezione; un piano pronto o non riuscito nel processo, dove si rilancia.
 */
export function notificationHref(notification: Notification): string {
  const process = ROUTES.projects.process(notification.projectId, notification.processId);
  switch (notification.kind) {
    case "conformance_findings":
      return `${process}?view=canvas`;
    case "simulation_done":
    case "simulation_failed":
      return ROUTES.projects.simulation(notification.projectId, notification.processId);
    default:
      return process;
  }
}

function toNotification(raw: z.infer<typeof apiNotificationSchema>): Notification {
  return {
    id: raw.id,
    kind: raw.kind,
    occurredAt: raw.occurred_at,
    read: raw.read,
    processId: raw.process_id,
    processName: raw.process_name,
    projectId: raw.project_id,
    projectName: raw.project_name,
    clientName: raw.client_name,
    count: raw.count,
    version: raw.version,
    detail: raw.detail,
    runId: raw.run_id,
  };
}

export async function fetchNotifications(): Promise<NotificationFeed> {
  const data = await http<unknown>("/v1/workspace/notifications");
  const parsed = apiResponseSchema.parse(data);
  return { items: parsed.items.map(toNotification), unread: parsed.unread };
}

/** Segna come letti gli avvisi indicati; senza id, tutti quelli mostrati. */
export async function markNotificationsRead(ids: string[]): Promise<NotificationFeed> {
  const data = await http<unknown>("/v1/workspace/notifications/read", {
    method: "POST",
    body: { ids },
  });
  const parsed = apiResponseSchema.parse(data);
  return { items: parsed.items.map(toNotification), unread: parsed.unread };
}

export function useNotificationsQuery(): UseQueryResult<NotificationFeed> {
  return useQuery({
    queryKey: notificationKeys.all,
    queryFn: fetchNotifications,
    // Il lavoro in differita finisce mentre il consulente guarda altro: senza
    // un controllo periodico la campanella direbbe la verita' solo a F5.
    refetchInterval: 60_000,
    staleTime: 30_000,
    // Nessun ritentativo automatico: col backend giu' il ritentativo teneva il
    // pannello su "Carico gli avvisi..." per parecchi secondi, che e' il modo
    // peggiore di dire "non lo so". Il giro dopo ci riprova da solo.
    retry: false,
  });
}

export function useMarkNotificationsRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ids: string[]) => markNotificationsRead(ids),
    onSuccess: (feed) => queryClient.setQueryData(notificationKeys.all, feed),
  });
}
