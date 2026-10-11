import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import type { ProjectProcess } from "@/contracts/workspace";
import { useBpmnVersionsQuery, useConformanceStatusQuery, useProcessProvenanceQuery } from "../api";
import { useImpactReview } from "../review/api";
import { readReviewGraph, type ReviewNode } from "../review/reviewModel";
import { listProsimosSimulationRuns } from "../simulation/simulationApi";
import {
  buildReadiness, buildTimeline, changesWithEvidence, latestCompletedRun, openPoints, stageFromStatus,
} from "./handoverModel";
import { readPlainProcess } from "./plainProcess";

/**
 * Tutto cio' che la consegna sa del processo, letto una volta sola. La pagina
 * del consulente e il cruscotto del responsabile passano di qui, cosi' non
 * possono raccontare due versioni diverse dello stesso processo.
 */
export function useHandoverData(process: ProjectProcess) {
  const reviewQ = useImpactReview(process.id, process.bpmnModelId);
  const provenanceQ = useProcessProvenanceQuery(process.id);
  const conformanceQ = useConformanceStatusQuery(process.id);
  const versionsQ = useBpmnVersionsQuery(process.bpmnModelId, { enabled: Boolean(process.bpmnModelId) });
  // Stessa chiave della sezione Simulazione: la cache e' condivisa.
  const runsQ = useQuery({
    queryKey: ["workspace", "simulation-runs", process.bpmnModelId],
    queryFn: () => listProsimosSimulationRuns(process.bpmnModelId),
    enabled: Boolean(process.bpmnModelId),
  });

  const owner = process.owner.trim();
  const review = reviewQ.data;
  const provenance = provenanceQ.data;
  const conformance = conformanceQ.data;
  const runs = useMemo(() => runsQ.data ?? [], [runsQ.data]);
  const versions = useMemo(() => versionsQ.data ?? [], [versionsQ.data]);
  const xml = review?.xml ?? null;

  const readiness = useMemo(
    () => buildReadiness({ owner, review, provenance, conformance, runs }),
    [owner, review, provenance, conformance, runs],
  );
  const changes = useMemo(() => changesWithEvidence(review, provenance), [review, provenance]);
  const points = useMemo(() => openPoints(review), [review]);
  const timeline = useMemo(() => buildTimeline(versions, review), [versions, review]);
  const plain = useMemo(() => readPlainProcess(xml), [xml]);
  const nodes = useMemo<ReviewNode[]>(() => {
    try { return readReviewGraph(xml).nodes; } catch { return []; }
  }, [xml]);

  return {
    stage: stageFromStatus(process.status),
    owner,
    review,
    reviewLoading: reviewQ.isLoading,
    hasConformanceReport: Boolean(conformance?.report),
    runs,
    runsLoading: runsQ.isLoading,
    checksLoading: reviewQ.isLoading || provenanceQ.isLoading || conformanceQ.isLoading || runsQ.isLoading,
    readiness,
    changes,
    points,
    timeline,
    plain,
    nodes,
    latestRun: latestCompletedRun(runs),
    latestVersion: versions.reduce<(typeof versions)[number] | undefined>((a, b) => (!a || b.id > a.id ? b : a), undefined),
    findings: review?.plan?.consultant_findings ?? [],
  };
}

/** Data breve nella lingua dell'interfaccia; vuota se la data non si legge. */
export function formatDay(value: string | null | undefined, language: string): string {
  const parsed = value ? new Date(value) : null;
  return parsed && !Number.isNaN(parsed.getTime())
    ? new Intl.DateTimeFormat(language, { day: "numeric", month: "short", year: "numeric" }).format(parsed)
    : "";
}
