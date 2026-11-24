import React from "react";
import { useTranslation } from "react-i18next";
import { Map as MapIcon } from "lucide-react";

import { InlineNotice } from "@/components/feedback";
import { HttpError, httpErrorCode, httpErrorMessage } from "@/lib/http";
import { Button } from "@/ui/button";
import { Skeleton } from "@/ui/skeleton";

import type { NodeDecoration } from "../canvas/SimulationCanvas";
import { formatCount, formatPercent } from "../simulationResults";
import { adherence, deviationLevel, deviationRows, offPathVariants } from "./conformanceView";
import { FIDELITY_BADGE_TONE, type OnLogOverlay } from "./logOverlay";
import { useEventLogConformance } from "./useEventLogImport";

const LEGEND = { label: "simulation.eventLog.conformance.legend", levels: "simulation.eventLog.conformance.legendLevel" };
const UNAVAILABLE_REASONS = ["not_mapped", "no_model", "model_not_replayable"] as const;
type UnavailableReason = (typeof UNAVAILABLE_REASONS)[number];

/**
 * CONF-02: i casi reali rigiocati sul disegno. Dice quanti seguono il processo,
 * quali passi vengono saltati o anticipati e quali percorsi reali escono dal
 * modello. Il numero tecnico (fitness del token replay) sta nei dettagli.
 */
export function ConformanceStep({ eventLogId, mappedAt, onDecorations, onReviewActivities, onNext }: {
  eventLogId: string;
  mappedAt: string | null;
  onDecorations?: OnLogOverlay;
  onReviewActivities: () => void;
  onNext: () => void;
}): React.JSX.Element {
  const { t, i18n } = useTranslation("process");
  const lang = i18n.language?.startsWith("it") ? "it" : "en";
  const query = useEventLogConformance(eventLogId, mappedAt);
  const [onCanvas, setOnCanvas] = React.useState(false);
  const result = query.data ?? null;
  const rows = React.useMemo(() => (result ? deviationRows(result) : []), [result]);
  const variants = React.useMemo(() => (result ? offPathVariants(result) : []), [result]);
  const decorations = React.useMemo<NodeDecoration[]>(
    () => rows.map((row) => {
      const tone = deviationLevel(row.share);
      return { elementId: row.elementId, markers: [`sim-fidelity-${tone}`], badge: formatPercent(row.share), badgeTone: FIDELITY_BADGE_TONE[tone] };
    }),
    [rows],
  );
  React.useEffect(() => { onDecorations?.(onCanvas ? { items: decorations, legend: LEGEND } : null); }, [onCanvas, decorations, onDecorations]);
  React.useEffect(() => () => onDecorations?.(null), [onDecorations]);

  const cases = (count: number) => t("simulation.eventLog.conformance.cases", { count, value: formatCount(count, lang) });
  const reviewButton = <Button size="sm" variant="outline" onClick={onReviewActivities}>{t("simulation.eventLog.conformance.reviewActivities")}</Button>;
  const nextButton = <div className="sim-eventlog-actions"><Button size="sm" onClick={onNext}>{t("simulation.eventLog.next")}</Button></div>;
  const level = result ? adherence(result.fitting_share) : "far";

  return (
    <section className="sim-eventlog-step" aria-label={t("simulation.eventLog.step.conformance")} aria-busy={query.isPending || undefined}>
      {query.isPending ? <Skeleton className="h-24 w-full" /> : query.isError ? (
        <ConformanceError error={query.error} reviewButton={reviewButton} onRetry={() => void query.refetch()} />
      ) : !result ? null : result.cases === 0 ? (
        <>
          <InlineNotice tone="warning" title={t("simulation.eventLog.conformance.noCases")} />
          {nextButton}
        </>
      ) : (
        <>
          <p className="sim-eventlog-hint">{t("simulation.eventLog.conformance.intro")}</p>
          {result.bpmn_version_id !== result.mapping_bpmn_version_id && (
            <InlineNotice tone="warning" title={t("simulation.eventLog.conformance.modelChanged")} action={reviewButton} />
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
                    <td>{row.skipped ? cases(row.skipped) : "—"}</td>
                    <td>{row.outOfOrder ? cases(row.outOfOrder) : "—"}</td>
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
                    <strong>{cases(variant.cases)}</strong>
                    <span className="sim-conformance-trace">{variant.steps.join(" → ")}</span>
                    {variant.skipped.length > 0 && <small>{t("simulation.eventLog.conformance.pathSkipped", { steps: variant.skipped.join(", ") })}</small>}
                    {variant.early.length > 0 && <small>{t("simulation.eventLog.conformance.pathEarly", { steps: variant.early.join(", ") })}</small>}
                    {variant.unmodeled.length > 0 && <small>{t("simulation.eventLog.conformance.pathUnmodeled", { steps: variant.unmodeled.join(", ") })}</small>}
                  </li>
                ))}
              </ol>
            </>
          )}

          {Object.keys(result.unmodeled_activities).length > 0 && (
            <InlineNotice tone="warning" title={t("simulation.eventLog.conformance.unmodeled")} action={reviewButton}>
              <ul>{Object.entries(result.unmodeled_activities).map(([name, count]) => <li key={name}>{name} · {cases(count)}</li>)}</ul>
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
            {result.warnings.length > 0 && (
              <ul className="sim-eventlog-hint">
                {result.warnings.map((warning, index) => (
                  <li key={index}>{t(`simulation.eventLog.conformance.warning.${warning.code}`, { ...warning.params, defaultValue: warning.code })}</li>
                ))}
              </ul>
            )}
          </details>
          {nextButton}
        </>
      )}
    </section>
  );
}

/** 409: manca il modello o l'abbinamento, detto nella lingua dell'utente. Altro: errore e riprova. */
function ConformanceError({ error, reviewButton, onRetry }: { error: Error; reviewButton: React.ReactNode; onRetry: () => void }): React.JSX.Element {
  const { t } = useTranslation("process");
  if (!(error instanceof HttpError) || error.status !== 409) {
    return (
      <InlineNotice tone="error" title={t("simulation.eventLog.conformance.failed")}
        action={<Button size="sm" variant="outline" onClick={onRetry}>{t("simulation.eventLog.retry")}</Button>}>
        {httpErrorMessage(error, t("simulation.eventLog.conformance.failed"))}
      </InlineNotice>
    );
  }
  const code = httpErrorCode(error);
  const reason = UNAVAILABLE_REASONS.find((item): item is UnavailableReason => item === code);
  return (
    <InlineNotice tone="warning" title={t("simulation.eventLog.conformance.unavailable")} action={reason === "no_model" ? undefined : reviewButton}>
      {reason ? t(`simulation.eventLog.conformance.reason.${reason}`) : httpErrorMessage(error, t("simulation.eventLog.conformance.unavailable"))}
    </InlineNotice>
  );
}
