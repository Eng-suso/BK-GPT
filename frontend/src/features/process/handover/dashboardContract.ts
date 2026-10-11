import { z } from "zod";

import { buildTimeline, stageFromStatus, type HandoverStage, type TimelineEvent } from "./handoverModel";
import { readPlainProcess, type PlainProcess } from "./plainProcess";

/**
 * Il cruscotto del responsabile come lo manda il server, sia all'anteprima
 * del consulente sia al link del cliente. Nessun import di rete qui: questo
 * file entra anche nella pagina del cliente, che non deve mai contenere il
 * codice con le credenziali dello studio.
 */
export const ownerDashboardSchema = z.object({
  process: z.object({ name: z.string(), owner: z.string(), status: z.string(), stage: z.string() }),
  project_name: z.string(),
  client_name: z.string(),
  xml: z.string().nullable(),
  changes: z.array(z.object({
    id: z.string(), node_id: z.string(), node_name: z.string(), title: z.string(), detail: z.string(), created_at: z.string(),
  })),
  open_points: z.array(z.object({
    id: z.string(), node_id: z.string(), node_name: z.string(), title: z.string(), kind: z.enum(["clarification", "deferred"]), created_at: z.string(),
  })),
  versions: z.array(z.object({ id: z.number(), change_summary: z.string(), created_at: z.string() })),
  results: z.object({
    scenario_name: z.string(), completed_at: z.string().nullable(),
    cycle_avg_seconds: z.number(), waiting_avg_seconds: z.number(), cost_per_case: z.number(),
  }).nullable(),
  generated_at: z.string(),
});

export type OwnerDashboardPayload = z.infer<typeof ownerDashboardSchema>;

export type OwnerDashboardData = {
  processName: string;
  owner: string;
  stage: HandoverStage;
  projectName: string;
  clientName: string;
  plain: PlainProcess;
  changes: OwnerDashboardPayload["changes"];
  openPoints: OwnerDashboardPayload["open_points"];
  timeline: TimelineEvent[];
  results: OwnerDashboardPayload["results"];
  latestVersion: { id: number; createdAt: string } | null;
  generatedAt: string;
};

/** Dalla risposta del server a cio' che la pagina mostra. */
export function toOwnerDashboard(raw: unknown): OwnerDashboardData {
  const payload = ownerDashboardSchema.parse(raw);
  const versions = payload.versions.map((version) => ({ id: version.id, changeSummary: version.change_summary, createdAt: version.created_at }));
  const latest = versions.reduce<(typeof versions)[number] | null>((a, b) => (!a || b.id > a.id ? b : a), null);
  return {
    processName: payload.process.name,
    owner: payload.process.owner.trim(),
    // Lo stato arriva dal vocabolario del backend; uno sconosciuto vale "in preparazione".
    stage: stageFromStatus(payload.process.status as Parameters<typeof stageFromStatus>[0]),
    projectName: payload.project_name,
    clientName: payload.client_name,
    plain: readPlainProcess(payload.xml),
    changes: payload.changes,
    openPoints: payload.open_points,
    timeline: buildTimeline(versions, [
      ...payload.changes.map((change) => ({ ...change, kind: "candidate" as const })),
      ...payload.open_points,
    ]),
    results: payload.results,
    latestVersion: latest ? { id: latest.id, createdAt: latest.createdAt } : null,
    generatedAt: payload.generated_at,
  };
}
