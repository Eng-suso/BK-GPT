import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { CircleHelp, FileText, GitPullRequest, MessageSquare, PauseCircle, UserRound } from "lucide-react";

import { StatTile } from "@/components/data/StatTile";
import { StatusIndicator } from "@/components/status/StatusIndicator";
import type { StatusTone } from "@/components/status/tones";
import { Surface } from "@/ui/surface";
import { formatCurrency, formatDuration } from "../simulation/simulationResults";
import type { OwnerDashboardData } from "./dashboardContract";
import type { HandoverStage, TimelineEvent } from "./handoverModel";
import { PlainProcessSection } from "./PlainProcessSection";
import "./handover.css";

const STAGE_TONE: Record<HandoverStage, StatusTone> = { design: "neutral", review: "pending", approved: "ok" };
const EVENT_ICON: Record<TimelineEvent["kind"], typeof FileText> = {
  version: FileText, change: GitPullRequest, request: MessageSquare, deferred: PauseCircle,
};

/** Data breve nella lingua dell'interfaccia; vuota se la data non si legge. */
function formatDay(value: string | null | undefined, language: string): string {
  const parsed = value ? new Date(value) : null;
  return parsed && !Number.isNaN(parsed.getTime())
    ? new Intl.DateTimeFormat(language, { day: "numeric", month: "short", year: "numeric" }).format(parsed)
    : "";
}

/**
 * Il cruscotto che legge il responsabile del processo presso il cliente. Solo
 * presentazione: riceve i dati gia' pronti, cosi' l'anteprima del consulente e
 * la pagina del link mostrano esattamente la stessa cosa. Non importa nulla
 * che parli con il server.
 */
export function OwnerDashboardView({ data, toolbar }: { data: OwnerDashboardData; toolbar: ReactNode }): React.JSX.Element {
  const { t, i18n } = useTranslation("process");
  const lang = i18n.language?.startsWith("it") ? "it" : "en";
  const day = (value: string | null | undefined) => formatDay(value, i18n.language);
  const plainNumber = new Map(data.plain.steps.map((step) => [step.id, step.number]));
  const changedTitles = new Map<string, string[]>();
  for (const change of data.changes) changedTitles.set(change.node_id, [...(changedTitles.get(change.node_id) ?? []), change.title]);
  const results = data.results ? [
    { id: "cycle", label: t("handover.dashboard.resultCycle"), value: formatDuration(data.results.cycle_avg_seconds, lang) },
    { id: "waiting", label: t("handover.dashboard.resultWaiting"), value: formatDuration(data.results.waiting_avg_seconds, lang) },
    { id: "cost", label: t("handover.dashboard.resultCost"), value: formatCurrency(data.results.cost_per_case, lang) },
  ] : [];

  return (
    <div className="owner-dashboard ui-scrollbar">
      {toolbar}
      <main className="owner-dashboard-page">
        <header className="owner-dashboard-header">
          <p className="owner-dashboard-eyebrow">{t("handover.dashboard.title")} · {[data.clientName, data.projectName].filter(Boolean).join(" · ")}</p>
          <h1>{data.processName}</h1>
          <div className="owner-dashboard-meta">
            <span className="inline-flex items-center gap-1.5"><UserRound aria-hidden className="size-3.5" />{t("handover.dashboard.preparedFor", { owner: data.owner || t("handover.noOwner") })}</span>
            {data.latestVersion && <span>{t("handover.dashboard.version", { id: data.latestVersion.id, date: day(data.latestVersion.createdAt) })}</span>}
            <span>{t("handover.dashboard.updated", { date: day(data.generatedAt) })}</span>
          </div>
        </header>

        <Surface variant="panel" className="owner-dashboard-status" data-stage={data.stage}>
          <StatusIndicator tone={STAGE_TONE[data.stage]} label={t(`handover.dashboard.status.${data.stage}`)} className="owner-dashboard-status-label" />
          <p>{t(`handover.dashboard.statusDetail.${data.stage}`)}</p>
          {data.consultantName && <p className="owner-dashboard-consultant"><UserRound aria-hidden className="size-3.5" />{t("handover.dashboard.consultant", { name: data.consultantName })}</p>}
        </Surface>

        <section className="handover-section" aria-labelledby="owner-glance">
          <h2 id="owner-glance" className="sr-only">{t("handover.dashboard.glance.title")}</h2>
          <div className="owner-dashboard-glance">
            <StatTile label={t("handover.dashboard.glance.steps")} value={data.plain.steps.filter((step) => step.kind === "activity").length} />
            <StatTile label={t("handover.dashboard.glance.people")} value={data.plain.actors.length} />
            <StatTile label={t("handover.dashboard.glance.changes")} value={data.changes.length} />
          </div>
        </section>

        <PlainProcessSection plain={data.plain} changedTitles={changedTitles} />

        <section className="handover-section" aria-labelledby="owner-results">
          <header className="handover-section-heading">
            <h2 id="owner-results">{t("handover.dashboard.results")}</h2>
            {data.results && <p>{t("handover.dashboard.resultsNote", { scenario: data.results.scenario_name })}</p>}
          </header>
          {results.length === 0 ? (
            <Surface variant="inset" className="handover-empty">{t("handover.dashboard.resultsEmpty")}</Surface>
          ) : (
            <div className="owner-dashboard-results">
              {results.map((row) => <StatTile key={row.id} label={row.label} value={row.value} className="owner-dashboard-result" />)}
            </div>
          )}
        </section>

        <section className="handover-section" aria-labelledby="owner-changes">
          <header className="handover-section-heading"><h2 id="owner-changes">{t("handover.dashboard.changes")}</h2></header>
          {data.changes.length === 0 ? (
            <Surface variant="inset" className="handover-empty">{t("handover.dashboard.changesEmpty")}</Surface>
          ) : (
            <ol className="handover-list">
              {data.changes.map((change) => (
                <li key={change.id}><Surface asChild variant="panel"><article className="handover-change">
                  <div className="handover-change-context">{plainNumber.has(change.node_id)
                    ? <a href={`#plain-step-${plainNumber.get(change.node_id)}`} className="owner-dashboard-step-link" aria-label={t("handover.dashboard.goToStep", { n: plainNumber.get(change.node_id) })}>{t("handover.dashboard.stepRef", { n: plainNumber.get(change.node_id), name: change.node_name })}</a>
                    : <span>{change.node_name}</span>}</div>
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
            {data.timeline.length === 0 ? <Surface variant="inset" className="handover-empty">{t("handover.dashboard.activityEmpty")}</Surface> : (
              <Surface asChild variant="panel"><ol className="owner-dashboard-timeline">
                {data.timeline.map((event) => {
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
            {data.openPoints.length === 0 ? <Surface variant="inset" className="handover-empty">{t("handover.dashboard.openPointsEmpty")}</Surface> : (
              <Surface asChild variant="panel"><ul className="handover-checks">
                {data.openPoints.map((point) => (
                  <li key={point.id} className="handover-point">
                    <CircleHelp aria-hidden className="mt-0.5 size-4 shrink-0 text-[var(--domain-validation-warning-icon)]" />
                    <div className="min-w-0"><p className="handover-point-title">{point.title}</p><p className="handover-point-detail">{plainNumber.has(point.node_id) ? t("handover.dashboard.stepRef", { n: plainNumber.get(point.node_id), name: point.node_name }) : point.node_name}</p></div>
                  </li>
                ))}
              </ul></Surface>
            )}
          </section>
        </div>

        <footer className="owner-dashboard-footer">
          <p>{data.consultantName ? t("handover.dashboard.replyTo", { name: data.consultantName }) : t("handover.dashboard.contact")}</p>
          <p>{t("handover.dashboard.footer")}</p>
        </footer>
      </main>
    </div>
  );
}
