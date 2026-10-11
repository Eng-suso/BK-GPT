import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  ArrowLeft, CircleCheck, CircleHelp, CircleX, FlaskConical, GitPullRequest, Send, TriangleAlert, Undo2, UserRound, Workflow,
} from "lucide-react";

import { ROUTES } from "@/app/routes";
import { ConfirmDialog, ErrorState } from "@/components/feedback";
import { StatTile } from "@/components/data";
import { WorkspaceContextBar } from "@/components/layout/CanvasWorkspace";
import { StatusIndicator, type StatusTone } from "@/components/status";
import type { ProcessStatus, ProjectProcess } from "@/contracts/workspace";
import { useProjectQuery, useUpdateProcessMutation } from "@/features/projects/api";
import { Badge } from "@/ui/badge";
import { Button } from "@/ui/button";
import { Skeleton } from "@/ui/skeleton";
import { Surface } from "@/ui/surface";
import { useBpmnVersionsQuery, useConformanceStatusQuery, useProcessProvenanceQuery } from "../api";
import { useImpactReview } from "../review/api";
import { readReviewGraph, type ReviewNode } from "../review/reviewModel";
import { listProsimosSimulationRuns } from "../simulation/simulationApi";
import { formatCurrency, formatDuration } from "../simulation/simulationResults";
import {
  buildReadiness, changesWithEvidence, latestCompletedRun, openPoints, stageFromStatus, STATUS_FOR_STAGE,
  type HandoverStage, type ReadinessCheck,
} from "./handoverModel";
import { RequestChangesDialog } from "./RequestChangesDialog";
import "./handover.css";

const STAGE_TONE: Record<HandoverStage, StatusTone> = { design: "neutral", review: "pending", approved: "ok" };
const JOURNEY = ["design", "review", "operate"] as const;
const JOURNEY_FOR_STAGE: Record<HandoverStage, (typeof JOURNEY)[number]> = { design: "design", review: "review", approved: "operate" };
const CHECK_ICON = { pass: CircleCheck, warning: TriangleAlert, fail: CircleX } as const;

type Confirm = "send" | "approve" | "reopen" | null;

/**
 * La consegna del processo al suo responsabile: cosa cambia, perche', con
 * quali fonti, e la sua approvazione. Non e' una quarta vista del disegno, ma
 * il punto in cui il processo si trova dopo il disegno e la simulazione.
 */
export function HandoverPage(): React.JSX.Element {
  const { projectId = "", processId = "" } = useParams();
  const { t } = useTranslation("process");
  const navigate = useNavigate();
  const projectQ = useProjectQuery(projectId);
  const process = projectQ.data?.processItems.find((item) => item.id === processId);

  if (projectQ.isLoading) {
    return (
      <div className="flex flex-col gap-4 px-7 py-6" aria-busy="true" aria-label={t("handover.loading")}>
        <Skeleton className="h-8 w-72" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-[50vh] w-full" />
      </div>
    );
  }
  if (projectQ.isError || !projectQ.data || !process) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <ErrorState
          description={projectQ.isError ? t("state.loadError") : t("state.processNotFound")}
          onRetry={projectQ.isError ? () => void projectQ.refetch() : undefined}
          action={<Button variant="ghost" size="sm" onClick={() => navigate(ROUTES.projects.detail(projectId))}>{t("actions.backToProject")}</Button>}
        />
      </div>
    );
  }
  return <Handover projectId={projectId} process={process} />;
}

function Handover({ projectId, process }: { projectId: string; process: ProjectProcess }): React.JSX.Element {
  const { t, i18n } = useTranslation("process");
  const lang = i18n.language?.startsWith("it") ? "it" : "en";
  const navigate = useNavigate();
  const stage = stageFromStatus(process.status);
  const owner = process.owner.trim();

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
  const updateProcess = useUpdateProcessMutation();
  const [confirm, setConfirm] = useState<Confirm>(null);
  const [requesting, setRequesting] = useState(false);

  const runs = useMemo(() => runsQ.data ?? [], [runsQ.data]);
  const review = reviewQ.data;
  const readiness = useMemo(
    () => buildReadiness({ owner, review, provenance: provenanceQ.data, conformance: conformanceQ.data, runs }),
    [owner, review, provenanceQ.data, conformanceQ.data, runs],
  );
  const changes = useMemo(() => changesWithEvidence(review, provenanceQ.data), [review, provenanceQ.data]);
  const points = useMemo(() => openPoints(review), [review]);
  const xml = review?.xml ?? null;
  const nodes = useMemo<ReviewNode[]>(() => {
    try { return readReviewGraph(xml).nodes; } catch { return []; }
  }, [xml]);
  const latestRun = latestCompletedRun(runs);
  const latestVersion = versionsQ.data?.reduce((a, b) => (b.id > a.id ? b : a), versionsQ.data[0]);
  const findings = review?.plan?.consultant_findings ?? [];
  const checksLoading = reviewQ.isLoading || provenanceQ.isLoading || conformanceQ.isLoading || runsQ.isLoading;

  const date = (value: string | null | undefined) => {
    const parsed = value ? new Date(value) : null;
    return parsed && !Number.isNaN(parsed.getTime())
      ? new Intl.DateTimeFormat(i18n.language, { day: "numeric", month: "short", year: "numeric" }).format(parsed) : "";
  };

  const moveTo = async (status: ProcessStatus, done: string) => {
    await updateProcess.mutateAsync({
      id: process.id,
      draft: { name: process.name, stage: process.stage, status, owner: process.owner, readiness: process.readiness },
    });
    toast.success(done);
  };

  const headline = stage === "approved" ? t("handover.headline.approved")
    : stage === "review" ? t("handover.headline.review", { owner: owner || t("handover.noOwner") })
      : checksLoading ? t("handover.loading")
        : readiness.ready ? t("handover.headline.ready") : t("handover.headline.notReady");

  return (
    <div className="flex h-full min-h-0 flex-col">
      <WorkspaceContextBar
        title={`${process.name} · ${t("handover.title")}`}
        navigation={<div className="flex shrink-0 items-center gap-2">
          <Button variant="ghost" size="icon-sm" onClick={() => navigate(ROUTES.projects.process(projectId, process.id))} aria-label={t("handover.back")} title={t("handover.back")}><ArrowLeft aria-hidden className="size-4" /></Button>
          <Badge variant="secondary">{process.stage}</Badge>
        </div>}
      />
      <div className="handover ui-scrollbar">
        <div className="handover-body">
          <Surface variant="panel" className="handover-status" data-stage={stage} data-ready={String(readiness.ready)} aria-live="polite">
            <div className="min-w-0">
              <h2>{headline}</h2>
              <div className="handover-status-meta">
                <StatusIndicator tone={STAGE_TONE[stage]} label={t(`handover.stage.${stage}`)} />
                <span className="inline-flex items-center gap-1.5"><UserRound aria-hidden className="size-3.5" />{owner || t("handover.noOwner")}</span>
                <span>{latestVersion ? t("handover.version", { id: latestVersion.id }) : t("handover.noVersion")}</span>
                {latestVersion && <span>{t("handover.updated", { date: date(latestVersion.createdAt) })}</span>}
              </div>
              {stage === "design" && !checksLoading && !readiness.ready && (
                <p className="mt-1 text-xs text-[var(--domain-validation-fail-text)]">{t("handover.notReadyDetail", { count: readiness.blocking })}</p>
              )}
            </div>
            <div className="handover-status-actions" role="group" aria-label={t("handover.actions.group")}>
              {stage === "design" && (
                <Button onClick={() => setConfirm("send")} disabled={checksLoading || !readiness.ready || updateProcess.isPending}><Send aria-hidden />{t("handover.actions.send")}</Button>
              )}
              {stage === "review" && <>
                <Button variant="outline" onClick={() => setRequesting(true)} disabled={updateProcess.isPending}><GitPullRequest aria-hidden />{t("handover.actions.requestChanges")}</Button>
                <Button onClick={() => setConfirm("approve")} disabled={updateProcess.isPending}><CircleCheck aria-hidden />{t("handover.actions.approve")}</Button>
              </>}
              {stage === "approved" && (
                <Button variant="outline" onClick={() => setConfirm("reopen")} disabled={updateProcess.isPending}><Undo2 aria-hidden />{t("handover.actions.reopen")}</Button>
              )}
            </div>
          </Surface>

          <ol className="handover-journey" aria-label={t("handover.journey.label")}>
            {JOURNEY.map((step) => (
              <li key={step} aria-current={JOURNEY_FOR_STAGE[stage] === step ? "step" : undefined}>
                <span className="handover-journey-who">{t(`handover.journey.${step}.who`)}{JOURNEY_FOR_STAGE[stage] === step && <span className="sr-only"> · {t("handover.journey.current")}</span>}</span>
                <span className="handover-journey-steps">{t(`handover.journey.${step}.steps`)}</span>
              </li>
            ))}
          </ol>

          <div className="handover-grid">
            <div className="handover-main">
              <section className="handover-section" aria-labelledby="handover-readiness">
                <header className="handover-section-heading"><h2 id="handover-readiness">{t("handover.readiness.title")}</h2><p>{t("handover.readiness.description")}</p></header>
                {checksLoading ? <Skeleton className="h-64 w-full" /> : (
                  <Surface asChild variant="panel"><ul className="handover-checks">
                    {readiness.checks.map((check) => <CheckRow key={check.id} check={check} owner={owner} hasReport={Boolean(conformanceQ.data?.report)} />)}
                  </ul></Surface>
                )}
              </section>

              <section className="handover-section" aria-labelledby="handover-changes">
                <header className="handover-section-heading"><h2 id="handover-changes">{t("handover.changes.title")}</h2><p>{t("handover.changes.description")}</p></header>
                {reviewQ.isLoading ? <Skeleton className="h-40 w-full" /> : changes.length === 0 ? (
                  <Surface variant="inset" className="handover-empty">{t("handover.changes.empty")}</Surface>
                ) : (
                  <ol className="handover-list">
                    {changes.map((change) => (
                      <li key={change.id}><Surface asChild variant="panel"><article className="handover-change">
                        <div className="handover-change-context"><Workflow aria-hidden className="size-3.5" /><span>{t("handover.changes.activity")}: {change.node_name}</span></div>
                        <h3>{change.title}</h3>
                        <dl>
                          {change.detail && <div><dt>{t("handover.changes.why")}</dt><dd>{change.detail}</dd></div>}
                          <div><dt>{t("handover.changes.sources")}</dt><dd>
                            {change.evidence.length === 0 ? <span className="text-muted-foreground">{t("handover.changes.noSources")}</span> : (
                              <div className="grid gap-2">{change.evidence.slice(0, 3).map((item, index) => (
                                <blockquote key={`${item.sourceName}-${index}`} className="handover-quote">{item.quote}<cite>{item.sourceName}</cite></blockquote>
                              ))}</div>
                            )}
                          </dd></div>
                        </dl>
                        {review && change.base_revision !== review.base_revision && <p className="text-xs text-[var(--domain-validation-warning-text)]">{t("handover.changes.outdated")}</p>}
                        <p className="handover-change-footer">{t("handover.changes.proposedBy", { who: change.created_by, date: date(change.created_at) })}</p>
                      </article></Surface></li>
                    ))}
                  </ol>
                )}
              </section>

              <section className="handover-section" aria-labelledby="handover-simulation">
                <header className="handover-section-heading">
                  <h2 id="handover-simulation">{t("handover.simulation.title")}</h2>
                  {latestRun && <p>{t("handover.simulation.description", { scenario: latestRun.scenario_name })}</p>}
                </header>
                {runsQ.isLoading ? <Skeleton className="h-20 w-full" /> : latestRun?.summary ? (
                  <div className="handover-stats">
                    <StatTile label={t("handover.simulation.cycle")} value={formatDuration(latestRun.summary.cycle.avg, lang)} />
                    <StatTile label={t("handover.simulation.waiting")} value={formatDuration(latestRun.summary.waiting.avg, lang)} />
                    <StatTile label={t("handover.simulation.cost")} value={formatCurrency(latestRun.summary.cost.perCase, lang)} />
                    <StatTile label={t("handover.simulation.cases")} value={latestRun.summary.casesCompleted.toLocaleString(i18n.language)} />
                  </div>
                ) : (
                  <Surface variant="inset" className="handover-empty">{t("handover.simulation.empty")}</Surface>
                )}
                <div><Button variant="link" size="sm" className="px-0" onClick={() => navigate(ROUTES.projects.simulation(projectId, process.id))}><FlaskConical aria-hidden />{t("handover.actions.openSimulation")}</Button></div>
              </section>

              <section className="handover-section" aria-labelledby="handover-open">
                <header className="handover-section-heading"><h2 id="handover-open">{t("handover.openPoints.title")}</h2></header>
                {points.length === 0 ? <Surface variant="inset" className="handover-empty">{t("handover.openPoints.empty")}</Surface> : (
                  <Surface asChild variant="panel"><ul className="handover-checks">
                    {points.map((point) => (
                      <li key={point.id} className="handover-point">
                        <CircleHelp aria-hidden className="mt-0.5 size-4 shrink-0 text-[var(--domain-validation-warning-icon)]" />
                        <div className="min-w-0">
                          <p className="handover-point-title">{point.title}</p>
                          <p className="handover-point-detail">{t(`handover.openPoints.kind.${point.kind}`)} · {point.node_name}{point.detail ? ` · ${point.detail}` : ""}</p>
                        </div>
                      </li>
                    ))}
                  </ul></Surface>
                )}
              </section>
            </div>

            <aside className="handover-side">
              <section className="handover-section" aria-labelledby="handover-summary">
                <header className="handover-section-heading"><h2 id="handover-summary">{t("handover.summary.title")}</h2></header>
                <div className="handover-stats">
                  <StatTile label={t("handover.summary.problems")} value={findings.length} />
                  <StatTile label={t("handover.summary.changes")} value={changes.length} />
                  <StatTile label={t("handover.summary.openPoints")} value={points.length} tone={points.length ? "warning" : "neutral"} />
                  <StatTile label={t("handover.summary.simulation")} value={runs.filter((run) => run.status === "completed").length} />
                </div>
                <Surface variant="panel" className="handover-owner">
                  <h3 className="text-[13px] font-semibold">{t("handover.summary.findings")}</h3>
                  {findings.length === 0 ? <p className="text-xs text-muted-foreground">{t("handover.summary.noFindings")}</p> : (
                    <ul className="handover-findings">{findings.slice(0, 5).map((item) => <li key={item.id}>{item.finding}</li>)}</ul>
                  )}
                </Surface>
              </section>

              <section className="handover-section" aria-labelledby="handover-owner">
                <header className="handover-section-heading"><h2 id="handover-owner">{t("handover.ownership.title")}</h2></header>
                <Surface variant="panel" className="handover-owner">
                  <div>
                    <span className="eyebrow block">{t("handover.ownership.owner")}</span>
                    <p className="handover-owner-name"><UserRound aria-hidden className="size-4" />{owner || t("handover.noOwner")}</p>
                  </div>
                  <div>
                    <span className="eyebrow block">{t("handover.ownership.afterApproval")}</span>
                    <ol className="mt-2 list-decimal">{(t("handover.ownership.steps", { returnObjects: true }) as string[]).map((step) => <li key={step}>{step}</li>)}</ol>
                  </div>
                  <Button variant="outline" size="sm" onClick={() => navigate(`${ROUTES.projects.process(projectId, process.id)}?view=canvas`)}><Workflow aria-hidden />{t("handover.actions.openModel")}</Button>
                </Surface>
              </section>
            </aside>
          </div>
        </div>
      </div>

      <ConfirmDialog
        open={confirm === "send"}
        onOpenChange={(open) => !open && setConfirm(null)}
        title={t("handover.confirm.sendTitle", { owner: owner || t("handover.noOwner") })}
        description={t("handover.confirm.sendBody")}
        confirmLabel={t("handover.actions.send")}
        onConfirm={() => moveTo(STATUS_FOR_STAGE.review, t("handover.done.sent"))}
      />
      <ConfirmDialog
        open={confirm === "approve"}
        onOpenChange={(open) => !open && setConfirm(null)}
        title={t("handover.confirm.approveTitle")}
        description={t("handover.confirm.approveBody")}
        confirmLabel={t("handover.actions.approve")}
        onConfirm={() => moveTo(STATUS_FOR_STAGE.approved, t("handover.done.approved"))}
      />
      <ConfirmDialog
        open={confirm === "reopen"}
        onOpenChange={(open) => !open && setConfirm(null)}
        title={t("handover.confirm.reopenTitle")}
        description={t("handover.confirm.reopenBody")}
        confirmLabel={t("handover.actions.reopen")}
        onConfirm={() => moveTo(STATUS_FOR_STAGE.design, t("handover.done.reopened"))}
      />
      {review && (
        <RequestChangesDialog
          processId={process.id}
          revision={review.base_revision}
          nodes={nodes}
          open={requesting}
          onOpenChange={setRequesting}
          onSaved={() => moveTo(STATUS_FOR_STAGE.design, t("handover.done.changes"))}
        />
      )}
    </div>
  );
}

function CheckRow({ check, owner, hasReport }: { check: ReadinessCheck; owner: string; hasReport: boolean }): React.JSX.Element {
  const { t } = useTranslation("process");
  const Icon = CHECK_ICON[check.outcome];
  const base = `handover.readiness.${check.id}`;
  const detail = (() => {
    switch (check.id) {
      case "owner": return check.outcome === "pass" ? owner : t(`${base}.fail`);
      case "sources": return !hasReport && check.outcome === "warning" ? t(`${base}.unchecked`) : t(`${base}.${check.outcome}`, { count: check.count });
      case "evidence": return check.count == null ? t(`${base}.unknown`) : t(`${base}.${check.outcome}`, { count: check.count });
      default: return t(`${base}.${check.outcome}`, { count: check.count });
    }
  })();
  return (
    <li className="handover-check" data-outcome={check.outcome}>
      <Icon aria-hidden className="handover-check-icon size-4" />
      <div className="min-w-0">
        <p className="handover-check-label">{t(`${base}.label`)}<span className="sr-only"> · {t(`handover.readiness.outcome.${check.outcome}`)}</span></p>
        <p className="handover-check-detail">{detail}</p>
      </div>
      {check.critical && check.outcome === "fail" && <span className="handover-check-critical">{t("handover.readiness.critical")}</span>}
    </li>
  );
}
