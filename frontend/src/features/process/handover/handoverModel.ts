import type {
  ConformanceStatus,
  ProcessProvenance,
  ProcessStatus,
  ProvenanceElement,
} from "@/contracts/workspace";
import type { SimulationRun } from "../simulation/simulationTypes";
import { readReviewGraph, type ReviewAction, type ReviewState } from "../review/reviewModel";

/**
 * La consegna non e' una vista in piu': e' il punto in cui si trova il
 * processo dopo il disegno. Lo stato vive sul record del processo, con il
 * vocabolario che il backend gia' conosce, cosi' nessuno lo deve inventare.
 */
export type HandoverStage = "design" | "review" | "approved";

export function stageFromStatus(status: ProcessStatus): HandoverStage {
  if (status === "Validato") return "approved";
  if (status === "Da validare") return "review";
  return "design";
}

export const STATUS_FOR_STAGE: Record<HandoverStage, ProcessStatus> = {
  design: "In corso",
  review: "Da validare",
  approved: "Validato",
};

export type CheckId = "model" | "owner" | "sources" | "evidence" | "simulation" | "openPoints";
export type CheckOutcome = "pass" | "warning" | "fail";
export type ReadinessCheck = {
  id: CheckId;
  outcome: CheckOutcome;
  /** Un controllo critico non superato blocca l'invio al responsabile. */
  critical: boolean;
  /** Il numero che il testo racconta (passi, problemi, percentuale...). */
  count?: number;
};

export type Readiness = { checks: ReadinessCheck[]; ready: boolean; blocking: number };

export type ReadinessInput = {
  owner: string;
  review: ReviewState | null | undefined;
  provenance: ProcessProvenance | null | undefined;
  conformance: ConformanceStatus | null | undefined;
  runs: SimulationRun[];
};

const OPEN_POINT_KINDS: ReviewAction["kind"][] = ["clarification", "deferred"];

/** Le domande aperte e i punti rimandati: quello che resta da chiarire. */
export function openPoints(review: ReviewState | null | undefined): ReviewAction[] {
  return review?.actions.filter((action) => OPEN_POINT_KINDS.includes(action.kind)) ?? [];
}

/** Le modifiche proposte al processo, quelle che il responsabile approva. */
export function proposedChanges(review: ReviewState | null | undefined): ReviewAction[] {
  return review?.actions.filter((action) => action.kind === "candidate") ?? [];
}

/**
 * Controlla se il processo si puo' consegnare. Solo dati che esistono gia':
 * se un'informazione manca, il controllo lo dice invece di darlo per buono.
 */
export function buildReadiness(input: ReadinessInput): Readiness {
  const steps = safeTaskCount(input.review?.xml ?? null);
  const blockingIssues = input.conformance?.report?.findings.filter((f) => f.severity === "blocking").length ?? 0;
  const gaps = input.conformance?.report?.findings.filter((f) => f.severity === "gap").length ?? 0;
  const grounded = input.provenance ? Math.round(input.provenance.groundedRatio * 100) : null;
  const toConfirm = input.provenance?.awaitingConfirmation ?? 0;
  const simulated = input.runs.filter((run) => run.status === "completed").length;
  const open = openPoints(input.review).length;

  const checks: ReadinessCheck[] = [
    { id: "model", outcome: steps > 0 ? "pass" : "fail", critical: true, count: steps },
    { id: "owner", outcome: input.owner.trim() ? "pass" : "fail", critical: true },
    {
      id: "sources",
      outcome: blockingIssues > 0 ? "fail" : gaps > 0 || !input.conformance?.report ? "warning" : "pass",
      critical: true,
      count: blockingIssues > 0 ? blockingIssues : gaps,
    },
    {
      id: "evidence",
      outcome: grounded == null ? "warning" : grounded >= 80 && toConfirm === 0 ? "pass" : grounded >= 50 ? "warning" : "fail",
      critical: false,
      count: grounded ?? undefined,
    },
    { id: "simulation", outcome: simulated > 0 ? "pass" : "warning", critical: false, count: simulated },
    { id: "openPoints", outcome: open > 0 ? "warning" : "pass", critical: false, count: open },
  ];
  const blocking = checks.filter((check) => check.critical && check.outcome === "fail").length;
  return { checks, ready: blocking === 0, blocking };
}

function safeTaskCount(xml: string | null): number {
  try {
    return readReviewGraph(xml).nodes.length;
  } catch {
    return 0;
  }
}

export type ChangeEvidence = Pick<ProvenanceElement, "sourceName" | "quote" | "markStatus">;
export type HandoverChange = ReviewAction & { evidence: ChangeEvidence[] };

/**
 * Ogni modifica porta con se' le fonti del passo che tocca, cosi' il
 * responsabile vede perche' e' stata proposta senza chiederlo al consulente.
 * Il legame passa dagli identificativi del disegno, mai da nomi simili.
 */
export function changesWithEvidence(
  review: ReviewState | null | undefined,
  provenance: ProcessProvenance | null | undefined,
): HandoverChange[] {
  const changes = proposedChanges(review);
  if (!changes.length) return [];
  let refsByNode = new Map<string, string[]>();
  try {
    refsByNode = new Map(readReviewGraph(review?.xml ?? null).nodes.map((node) => [node.id, node.refs]));
  } catch {
    // Un disegno illeggibile non nasconde le modifiche: restano senza fonti.
  }
  return changes.map((change) => {
    const refs = refsByNode.get(change.node_id) ?? [];
    const evidence = (provenance?.elements ?? [])
      .filter((element) => refs.includes(element.sourceRef) && element.quote)
      .map(({ sourceName, quote, markStatus }) => ({ sourceName, quote, markStatus }));
    return { ...change, evidence };
  });
}

/** L'ultimo run concluso: i numeri che la consegna puo' citare. */
export function latestCompletedRun(runs: SimulationRun[]): SimulationRun | null {
  return [...runs]
    .filter((run) => run.status === "completed" && run.summary)
    .sort((a, b) => (b.completed_at ?? b.created_at).localeCompare(a.completed_at ?? a.created_at))[0] ?? null;
}
