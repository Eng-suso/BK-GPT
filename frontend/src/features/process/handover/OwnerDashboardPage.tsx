import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowLeft, CircleHelp, Download, FileText, GitPullRequest, MessageSquare, PauseCircle, UserRound } from "lucide-react";

import { ROUTES } from "@/app/routes";
import { ErrorState } from "@/components/feedback";
import { StatusIndicator, type StatusTone } from "@/components/status";
import type { ProjectProcess } from "@/contracts/workspace";
import { useProjectQuery } from "@/features/projects/api";
import { Button } from "@/ui/button";
import { Skeleton } from "@/ui/skeleton";
import { Surface } from "@/ui/surface";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/ui/table";
import { formatCurrency, formatDuration } from "../simulation/simulationResults";
import type { HandoverStage, TimelineEvent } from "./handoverModel";
import { formatDay, useHandoverData } from "./useHandoverData";
import "./handover.css";

const STAGE_TONE: Record<HandoverStage, StatusTone> = { design: "neutral", review: "pending", approved: "ok" };
const EVENT_ICON: Record<TimelineEvent["kind"], typeof FileText> = {
  version: FileText, change: GitPullRequest, request: MessageSquare, deferred: PauseCircle,
};

/**
 * Il cruscotto che riceve il responsabile del processo presso il cliente.
 * Il cliente non usa DeliR: oggi il consulente lo apre in anteprima e lo
 * manda in PDF; poi lo stesso cruscotto arrivera' con un link privato. Per
 * questo vive fuori dalla navigazione di DeliR e mostra solo cose che il
 * responsabile capisce senza il consulente accanto.
 */
export function OwnerDashboardPage(): React.JSX.Element {
  const { projectId = "", processId = "" } = useParams();
  const { t } = useTranslation("process");
  const navigate = useNavigate();
  const projectQ = useProjectQuery(projectId);
  const process = projectQ.data?.processItems.find((item) => item.id === processId);

  if (projectQ.isLoading) {
    return (
      <div className="owner-dashboard" aria-busy="true" aria-label={t("handover.loading")}>
        <div className="owner-dashboard-page"><Skeleton className="h-10 w-80" /><Skeleton className="h-28 w-full" /><Skeleton className="h-64 w-full" /></div>
      </div>
    );
  }
  if (projectQ.isError || !projectQ.data || !process) {
    return (
      <div className="flex h-dvh items-center justify-center">
        <ErrorState
          description={projectQ.isError ? t("state.loadError") : t("state.processNotFound")}
          onRetry={projectQ.isError ? () => void projectQ.refetch() : undefined}
          action={<Button variant="ghost" size="sm" onClick={() => navigate(ROUTES.projects.detail(projectId))}>{t("actions.backToProject")}</Button>}
        />
      </div>
    );
  }
  return <Dashboard projectId={projectId} projectName={projectQ.data.name} client={projectQ.data.client} process={process} />;
}

function Dashboard({ projectId, projectName, client, process }: { projectId: string; projectName: string; client: string; process: ProjectProcess }): React.JSX.Element {
  const { t, i18n } = useTranslation("process");
  const lang = i18n.language?.startsWith("it") ? "it" : "en";
  const navigate = useNavigate();
  const { stage, owner, reviewLoading, runsLoading, changes, points, timeline, latestRun, latestVersion } = useHandoverData(process);
  const day = (value: string | null | undefined) => formatDay(value, i18n.language);
  const summary = latestRun?.summary;
  const results = summary ? [
    { id: "cycle", label: t("handover.simulation.cycle"), value: formatDuration(summary.cycle.avg, lang) },
    { id: "waiting", label: t("handover.simulation.waiting"), value: formatDuration(summary.waiting.avg, lang) },
    { id: "cost", label: t("handover.simulation.cost"), value: formatCurrency(summary.cost.perCase, lang) },
  ] : [];

  return (
    <div className="owner-dashboard ui-scrollbar">
      <div className="owner-dashboard-toolbar" role="region" aria-label={t("handover.dashboard.preview")}>
        <Button variant="ghost" size="sm" onClick={() => navigate(ROUTES.projects.handover(projectId, process.id))}><ArrowLeft aria-hidden />{t("handover.dashboard.back")}</Button>
        <p className="owner-dashboard-preview">{t("handover.dashboard.preview")}</p>
        <Button size="sm" onClick={() => window.print()}><Download aria-hidden />{t("handover.dashboard.download")}</Button>
      </div>

      <main className="owner-dashboard-page">
        <header className="owner-dashboard-header">
          <p className="eyebrow">{t("handover.dashboard.title")} · {[client, projectName].filter(Boolean).join(" · ")}</p>
          <h1>{process.name}</h1>
          <div className="owner-dashboard-meta">
            <span className="inline-flex items-center gap-1.5"><UserRound aria-hidden className="size-3.5" />{t("handover.dashboard.preparedFor", { owner: owner || t("handover.noOwner") })}</span>
            {latestVersion && <span>{t("handover.dashboard.version", { id: latestVersion.id, date: day(latestVersion.createdAt) })}</span>}
            <span>{t("handover.dashboard.updated", { date: day(new Date().toISOString()) })}</span>
          </div>
        </header>

        <Surface variant="panel" className="owner-dashboard-status" data-stage={stage}>
          <StatusIndicator tone={STAGE_TONE[stage]} label={t(`handover.dashboard.status.${stage}`)} className="owner-dashboard-status-label" />
          <p>{t(`handover.dashboard.statusDetail.${stage}`)}</p>
        </Surface>

        <section className="handover-section" aria-labelledby="owner-results">
          <header className="handover-section-heading">
            <h2 id="owner-results">{t("handover.dashboard.results")}</h2>
            {latestRun && <p>{t("handover.dashboard.resultsDetail", { scenario: latestRun.scenario_name })}</p>}
          </header>
          {runsLoading ? <Skeleton className="h-32 w-full" /> : results.length === 0 ? (
            <Surface variant="inset" className="handover-empty">{t("handover.dashboard.resultsEmpty")}</Surface>
          ) : (
            <Surface variant="panel" className="owner-dashboard-table">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("handover.dashboard.indicator")}</TableHead>
                    <TableHead className="text-right">{t("handover.dashboard.expected")}</TableHead>
                    <TableHead className="text-right">{t("handover.dashboard.measured")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {results.map((row) => (
                    <TableRow key={row.id}>
                      <TableCell className="font-medium">{row.label}</TableCell>
                      <TableCell className="text-right tabular-nums">{row.value}</TableCell>
                      <TableCell className="text-right text-muted-foreground">{t("handover.dashboard.notMeasured")}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Surface>
          )}
        </section>

        <section className="handover-section" aria-labelledby="owner-changes">
          <header className="handover-section-heading"><h2 id="owner-changes">{t("handover.dashboard.changes")}</h2></header>
          {reviewLoading ? <Skeleton className="h-32 w-full" /> : changes.length === 0 ? (
            <Surface variant="inset" className="handover-empty">{t("handover.dashboard.changesEmpty")}</Surface>
          ) : (
            <ol className="handover-list">
              {changes.map((change) => (
                <li key={change.id}><Surface asChild variant="panel"><article className="handover-change">
                  <div className="handover-change-context"><span>{t("handover.changes.activity")}: {change.node_name}</span>{change.evidence.length > 0 && <span>· {t("handover.dashboard.sources", { count: change.evidence.length })}</span>}</div>
                  <h3>{change.title}</h3>
                  {change.detail && <dl><div><dt>{t("handover.dashboard.why")}</dt><dd>{change.detail}</dd></div></dl>}
                </article></Surface></li>
              ))}
            </ol>
          )}
        </section>

        <div className="owner-dashboard-columns">
          <section className="handover-section" aria-labelledby="owner-activity">
            <header className="handover-section-heading"><h2 id="owner-activity">{t("handover.dashboard.activity")}</h2></header>
            {timeline.length === 0 ? <Surface variant="inset" className="handover-empty">{t("handover.dashboard.activityEmpty")}</Surface> : (
              <Surface asChild variant="panel"><ol className="owner-dashboard-timeline">
                {timeline.map((event) => {
                  const Icon = EVENT_ICON[event.kind];
                  return (
                    <li key={event.id}>
                      <Icon aria-hidden className="owner-dashboard-timeline-icon size-4" />
                      <div className="min-w-0">
                        <p className="handover-point-title">{t(`handover.dashboard.event.${event.kind}`)}</p>
                        <p className="handover-point-detail">{[event.title, event.activity].filter(Boolean).join(" · ")}</p>
                      </div>
                      <time dateTime={event.at}>{day(event.at)}</time>
                    </li>
                  );
                })}
              </ol></Surface>
            )}
          </section>

          <section className="handover-section" aria-labelledby="owner-open">
            <header className="handover-section-heading"><h2 id="owner-open">{t("handover.dashboard.openPoints")}</h2></header>
            {points.length === 0 ? <Surface variant="inset" className="handover-empty">{t("handover.dashboard.openPointsEmpty")}</Surface> : (
              <Surface asChild variant="panel"><ul className="handover-checks">
                {points.map((point) => (
                  <li key={point.id} className="handover-point">
                    <CircleHelp aria-hidden className="mt-0.5 size-4 shrink-0 text-[var(--domain-validation-warning-icon)]" />
                    <div className="min-w-0"><p className="handover-point-title">{point.title}</p><p className="handover-point-detail">{point.node_name}</p></div>
                  </li>
                ))}
              </ul></Surface>
            )}
          </section>
        </div>

        <footer className="owner-dashboard-footer">
          <p>{t("handover.dashboard.contact")}</p>
          <p>{t("handover.dashboard.footer")}</p>
        </footer>
      </main>
    </div>
  );
}
