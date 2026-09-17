import { http } from "@/lib/http";

/**
 * Backend seam for the service status surface. Components never call `fetch`:
 * hooks build TanStack Query queries on top of these functions.
 */

export const statusKeys = {
  all: ["service-status"] as const,
  degradation: () => [...statusKeys.all, "degradation"] as const,
  queues: () => [...statusKeys.all, "queues"] as const,
};

export type DegradationReport = {
  status: "ok" | "degraded";
  /** `componente:esito` -> quante volte e' scattato il ripiego. */
  counters: Record<string, number>;
};

export type QueueStats = {
  pending?: number;
  stuck?: number;
  dead_letter?: number;
  /** La coda non ha risposto: il pannello lo dice invece di mostrare zero. */
  error?: string;
};

export type QueueHealth = {
  status: "ok" | "not_configured";
} & Record<string, QueueStats | string>;

/** Silent fallbacks the brain took: > 0 means something answered from a backup path. */
export function fetchDegradation(): Promise<DegradationReport> {
  return http<DegradationReport>("/v1/observability/degradation", {
    cache: "no-store",
  });
}

/** Projection queues (canonical -> Neo4j / Mem0), with what is waiting and what is stuck. */
export function fetchQueueHealth(): Promise<QueueHealth> {
  return http<QueueHealth>("/v1/observability/queues", { cache: "no-store" });
}

/** The queue names the backend reports, in the order the work flows through them. */
export const QUEUE_NAMES = [
  "kg_ingest_queue",
  "graph_outbox",
  "mem0_projection_log",
] as const;
