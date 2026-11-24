import React from "react";
import { useTranslation } from "react-i18next";
import { Map as MapIcon } from "lucide-react";

import { InlineNotice } from "@/components/feedback";
import { HttpError, httpErrorMessage } from "@/lib/http";
import { Button } from "@/ui/button";
import { Skeleton } from "@/ui/skeleton";

import type { NodeDecoration } from "../canvas/SimulationCanvas";
import { formatCount, formatPercent } from "../simulationResults";
import { adherence, CONFORMANCE_MARKER, deviationLevel, deviationRows, offPathVariants, type Adherence } from "./conformanceView";
import { useEventLogConformance } from "./useEventLogImport";

const BADGE_TONE: Record<Adherence, NodeDecoration["badgeTone"]> = { close: "neutral", calibrate: "warning", far: "danger" };

/**
 * CONF-02: i casi reali rigiocati sul disegno. Dice quanti seguono il processo,
 * quali passi vengono saltati o anticipati e quali percorsi reali escono dal
 * modello. Il numero tecnico (fitness del token replay) sta nei dettagli.
 */
export function ConformanceStep({ eventLogId, mappedAt, onDecorations, onReviewActivities, onNext }: {
  eventLogId: string;
  mappedAt: string | null;
  onDecorations?: (items: NodeDecoration[] | null) => void;
  onReviewActivities: () => void;
  onNext: () => void;
}): React.JSX.Element {
  const { t, i18n } = useTranslation("process");
  const lang = i18n.language?.startsWith("it") ? "it" : "en";
  const query = useEventLogConformance(eventLogId, mappedAt);
  const [onCanvas, setOnCanvas] = React.useState(false);
  const result = query.data ?? null;
  const rows = React.useMemo(() => (result ? deviationRows(result) : []), [result]);
  const decorations = React.useMemo<NodeDecoration[]>(
    () => rows.map((row) => {
      const tone = deviationLevel(row.share);
      return { elementId: row.elementId, markers: [`sim-fidelity-${tone}`, CONFORMANCE_MARKER], badge: formatPercent(row.share), badgeTone: BADGE_TONE[tone] };
    }),
    [rows],
  );
  React.useEffect(() => { onDecorations?.(onCanvas ? decorations : null); }, [onCanvas, decorations, onDecorations]);
  React.useEffect(() => () => onDecorations?.(null), [onDecorations]);

  const title = t("simulation.eventLog.step.conformance");
  if (query.isPending) {
    return <section className="sim-eventlog-step" aria-label={title} aria-busy="true"><Skeleton className="h-24 w-full" /></section>;
  }
  if (query.isError) {
    // 409: manca il modello o il mapping. Il codice stabile dice quale, nella lingua dell'utente.
    const error = query.error;
    const unavailable = error instanceof HttpError && error.status === 409;
    const reason = error instanceof HttpError && unavailable ? unavailableReason(error) : null;
    return (
      <section className="sim-eventlog-step" aria-label={title}>
        <InlineNotice
          tone={unavailable ? "warning" : "error"}
          title={t(unavailable ? "simulation.eventLog.conformance.unavailable" : "simulation.eventLog.conformance.failed")}
          action={unavailable
            ? reason === "no_model" ? undefined : <Button size="sm" variant="outline" onClick={onReviewActivities}>{t("simulation.eventLog.conformance.reviewActivities")}</Button>
            : <Button size="sm" variant="outline" onClick={() => void query.refetch()}>{t("simulation.eventLog.retry")}</Button>}
        >
          {reason ? t(`simulation.eventLog.conformance.reason.${reason}`) : httpErrorMessage(query.error, t("simulation.eventLog.conformance.failed"))}
        </InlineNotice>
      </section>
    );
  }
  if (!result) return <section className="sim-eventlog-step" aria-label={title} />;
  if (result.cases === 0) {
    return (
      <section className="sim-eventlog-step" aria-label={title}>
        <InlineNotice tone="warning" title={t("simulation.eventLog.conformance.noCases")} />
        <div className="sim-eventlog-actions"><Button size="sm" onClick={onNext}>{t("simulation.eventLog.next")}</Button></div>
      </section>
    );
  }

  const level = adherence(result.fitting_share);
  const variants = offPathVariants(result);
  const unmodeled = Object.entries(result.unmodeled_activities);
  const modelChanged = result.bpmn_version_id !== result.mapping_bpmn_version_id;
  return (
    <section className="sim-eventlog-step" aria-label={title}>
      <p className="sim-eventlog-hint">{t("simulation.eventLog.conformance.intro")}</p>
      {modelChanged && (
        <InlineNotice tone="warning" title={t("simulation.eventLog.conformance.modelChanged")}
          action={<Button size="sm" variant="outline" onClick={onReviewActivities}>{t("simulation.eventLog.conformance.reviewActivities")}</Button>} />
      )}

      <div className="sim-fidelity-verdict" data-fidelity={level} role="status">
        <strong>{t(`simulation.eventLog.conformance.verdict.${level}`)}</strong>
        <span>{t("simulation.eventLog.conformance.fitting", {
          count: result.fitting_cases,
          fitting: formatCount(result.fitting_cases, lang),
          total: formatCount(result.cases, lang),
          share: formatPercent(result.fitting_share),
        })}</span>
      </div>

      <div className="sim-eventlog-head sim-gap-head">
        <h3 className="sim-eventlog-title">{t("simulation.eventLog.conformance.where")}</h3>
        {rows.length > 0 && onDecorations && (
          <Button size="sm" variant={onCanvas ? "secondary" : "outline"} aria-pressed={onCanvas} onClick={() => setOnCanvas((value) => !value)}>
            <MapIcon aria-hidden className="size-4" />{t("simulation.eventLog.conformance.onCanvas")}
          </Button>
        )}
      </div>
      {rows.length === 0 ? (
        <p className="sim-eventlog-hint">{t("simulation.eventLog.conformance.noDeviations")}</p>
      ) : (
        <table className="sim-gap-table">
          <thead>
            <tr>
              <th scope="col">{t("simulation.eventLog.conformance.step")}</th>
              <th scope="col">{t("simulation.eventLog.conformance.skipped")}</th>
              <th scope="col">{t("simulation.eventLog.conformance.early")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.elementId}>
                <th scope="row">{row.name}</th>
                <td>{row.skipped ? t("simulation.eventLog.conformance.cases", { count: row.skipped, value: formatCount(row.skipped, lang) }) : "—"}</td>
                <td>{row.outOfOrder ? t("simulation.eventLog.conformance.cases", { count: row.outOfOrder, value: formatCount(row.outOfOrder, lang) }) : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {variants.length > 0 && (
        <>
          <h3 className="sim-eventlog-title">{t("simulation.eventLog.conformance.paths")}</h3>
          <ol className="sim-conformance-paths">
            {variants.map((variant, index) => (
              <li key={index}>
                <strong>{t("simulation.eventLog.conformance.cases", { count: variant.cases, value: formatCount(variant.cases, lang) })}</strong>
                <span className="sim-conformance-trace">{variant.steps.join(" → ")}</span>
                {variant.skipped.length > 0 && <small>{t("simulation.eventLog.conformance.pathSkipped", { steps: variant.skipped.join(", ") })}</small>}
                {variant.early.length > 0 && <small>{t("simulation.eventLog.conformance.pathEarly", { steps: variant.early.join(", ") })}</small>}
                {variant.unmodeled.length > 0 && <small>{t("simulation.eventLog.conformance.pathUnmodeled", { steps: variant.unmodeled.join(", ") })}</small>}
              </li>
            ))}
          </ol>
        </>
      )}

      {unmodeled.length > 0 && (
        <InlineNotice tone="warning" title={t("simulation.eventLog.conformance.unmodeled")}
          action={<Button size="sm" variant="outline" onClick={onReviewActivities}>{t("simulation.eventLog.conformance.reviewActivities")}</Button>}>
          <ul>{unmodeled.map(([name, cases]) => <li key={name}>{name} · {t("simulation.eventLog.conformance.cases", { count: cases, value: formatCount(cases, lang) })}</li>)}</ul>
        </InlineNotice>
      )}
      {result.unobserved_elements.length > 0 && (
        <p className="sim-eventlog-hint">
          {t("simulation.eventLog.conformance.unobserved", { steps: result.unobserved_elements.map((item) => item.name).join(", ") })}
        </p>
      )}

      <details className="sim-eventlog-advanced">
        <summary>{t("simulation.eventLog.conformance.details")}</summary>
        <dl className="sim-conformance-details">
          <div><dt>{t("simulation.eventLog.conformance.fitness")}</dt><dd>{result.fitness.toFixed(3)}</dd></div>
          <div><dt>{t("simulation.eventLog.conformance.method")}</dt><dd>{t("simulation.eventLog.conformance.methodValue")}</dd></div>
          {result.excluded_cases > 0 && (
            <div><dt>{t("simulation.eventLog.conformance.excluded")}</dt><dd>{formatCount(result.excluded_cases, lang)}</dd></div>
          )}
        </dl>
        <p className="sim-eventlog-hint">{t("simulation.eventLog.conformance.limits")}</p>
        {result.warnings.length > 0 && <ul className="sim-eventlog-hint">{result.warnings.map((warning, index) => <li key={index}>{t(`simulation.eventLog.conformance.warning.${warning.code}`, { ...warning.params, defaultValue: warning.code })}</li>)}</ul>}
      </details>
      <div className="sim-eventlog-actions"><Button size="sm" onClick={onNext}>{t("simulation.eventLog.next")}</Button></div>
    </section>
  );
}

const UNAVAILABLE_REASONS = ["not_mapped", "no_model", "model_not_replayable"] as const;
type UnavailableReason = (typeof UNAVAILABLE_REASONS)[number];

/** Il codice stabile della busta d'errore del server, se e' uno di quelli noti. */
function unavailableReason(error: HttpError): UnavailableReason | null {
  const code = (error.body as { error?: { code?: unknown } } | undefined)?.error?.code;
  return UNAVAILABLE_REASONS.find((item) => item === code) ?? null;
}
