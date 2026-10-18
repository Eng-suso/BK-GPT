import React from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle, ArrowRight, BarChartHorizontal, Info } from "lucide-react";

import { Meter, type MeterTone } from "@/components/data";
import { StatusIndicator, type StatusTone } from "@/components/status";
import { Button } from "@/ui/button";
import { cn } from "@/lib/utils";

import { SENSITIVITY_DELTA, type SensitivityFactor } from "./sensitivity";
import type { SourceConflict } from "./sourceConflicts";
import { formatParameterDuration } from "./studio/activityParameters";
import type { Confidence, InputConfidence } from "./simulationProvenance";
import type { ScenarioProvenance } from "./simulationTypes";

const METER_TONE: Record<Confidence, MeterTone> = {
  high: "ok",
  medium: "warning",
  low: "danger",
};

const STATUS_TONE: Record<Confidence, StatusTone> = {
  high: "ok",
  medium: "warning",
  low: "danger",
};

/** SIM-18: la formula della prontezza, scritta dove la si legge. */
const FORMULA_LINES = ["parameter", "family", "bands", "overall", "calendars", "notCounted"] as const;

type ReadinessSummaryProps = {
  confidence: InputConfidence;
  provenance: ScenarioProvenance | null;
  /** Compact form for the Panoramica rail. */
  dense?: boolean;
  /** Deep-link to the full scenario builder / low-confidence fields. */
  onReview?: () => void;
  /** SIM-17: le attivita' su cui le fonti dicono durate diverse. */
  conflicts?: SourceConflict[];
  /** SIM-25: le ipotesi incerte e l'avvio dello studio di sensitivita'. */
  sensitivity?: { factors: SensitivityFactor[]; onStart: () => void; disabled?: boolean };
  className?: string;
};

export function ReadinessSummary({
  confidence,
  provenance,
  dense = false,
  onReview,
  sensitivity,
  conflicts = [],
  className,
}: ReadinessSummaryProps): React.JSX.Element {
  const { t } = useTranslation("process");
  const { readiness } = confidence;

  const openGatewayQuestions = (provenance?.elements ?? [])
    .filter((el) => el.kind === "gateway")
    .reduce((acc, el) => acc + (el.open_questions ?? 0), 0);

  return (
    <div
      className={cn(
        "flex flex-col gap-3",
        !dense && "ui-surface ui-surface-panel p-4",
        className,
      )}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="eyebrow">
            {dense ? t("simulation.readiness.compact") : t("simulation.readiness.title")}
          </p>
          {!dense && (
            <p className="mt-0.5 text-xs text-muted-foreground">
              {t("simulation.readiness.subtitle")}
            </p>
          )}
        </div>
        <StatusIndicator
          tone={STATUS_TONE[readiness.overall]}
          label={t(`simulation.provenance.confidence.${readiness.overall}`)}
          className="shrink-0 font-semibold uppercase tracking-wide"
        />
      </div>

      {!confidence.hasDiscovery && (
        <p className="flex items-start gap-2 rounded-md border border-border bg-muted/40 px-2.5 py-2 text-micro leading-snug text-muted-foreground">
          <Info aria-hidden className="mt-0.5 size-3.5 shrink-0" />
          {t("simulation.readiness.noDiscovery")}
        </p>
      )}

      {(confidence.hasDiscovery || !dense) && (
      <ul className="grid gap-2">
        {readiness.rows.map((row) => (
          <li key={row.key} className="grid gap-1">
            <div className="flex items-center justify-between gap-2 text-micro">
              <span className="font-medium text-foreground">
                {t(`simulation.readiness.row.${row.key}`)}
              </span>
              <span className="flex shrink-0 items-center gap-2">
                {!dense && row.flagged > 0 && (
                  <span className="text-[var(--state-warning-text)]">
                    {t("simulation.readiness.flagged", { count: row.flagged })}
                  </span>
                )}
                <span className="tabular-nums text-muted-foreground">{row.pct}%</span>
              </span>
            </div>
            <Meter value={row.pct} label={t(`simulation.readiness.row.${row.key}`)} tone={METER_TONE[row.confidence]} showValue={false} height={4} />
          </li>
        ))}
      </ul>
      )}

      {!dense && (
        <details className="group text-micro text-muted-foreground" data-readiness-formula>
          <summary className="cursor-pointer select-none font-medium text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm">
            {t("simulation.readiness.formula.title")}
          </summary>
          <ul className="mt-1.5 grid gap-1 leading-snug">
            {FORMULA_LINES.map((line) => <li key={line}>{t(`simulation.readiness.formula.${line}`)}</li>)}
          </ul>
        </details>
      )}

      {!dense && openGatewayQuestions > 0 && (
        <p className="text-micro text-[var(--state-warning-text)]">
          {t("simulation.readiness.gatewaysToValidate", { count: openGatewayQuestions })}
        </p>
      )}

      {!dense && provenance?.missing_information && provenance.missing_information.length > 0 && (
        <FactList
          title={t("simulation.readiness.missingInfo")}
          items={provenance.missing_information}
        />
      )}
      {!dense && provenance?.weak_points && provenance.weak_points.length > 0 && (
        <FactList
          title={t("simulation.readiness.weakPoints")}
          items={provenance.weak_points}
        />
      )}

      {!dense && conflicts.length > 0 && <SourceConflicts conflicts={conflicts} />}

      {!dense && sensitivity && (
        <div className="grid gap-1.5 rounded-md border border-border p-2.5" data-readiness-sensitivity>
          <p className="text-micro font-medium text-foreground">{t("simulation.sensitivity.launchTitle")}</p>
          <p className="text-micro leading-snug text-muted-foreground">
            {sensitivity.factors.length > 0
              ? t("simulation.sensitivity.launchHint", {
                count: sensitivity.factors.length,
                pct: Math.round(SENSITIVITY_DELTA * 100),
                runs: sensitivity.factors.length * 2 + 1,
              })
              : t("simulation.sensitivity.launchNone")}
          </p>
          {sensitivity.factors.length > 0 && (
            <Button type="button" size="sm" variant="outline" className="gap-1.5 self-start" disabled={sensitivity.disabled} onClick={sensitivity.onStart}>
              <BarChartHorizontal aria-hidden className="size-3.5" />
              {t("simulation.sensitivity.launch")}
            </Button>
          )}
        </div>
      )}

      {onReview && (
        <Button
          type="button"
          size="sm"
          variant={dense ? "ghost" : "outline"}
          className={cn("mt-1 gap-1.5", dense && "h-7 self-start px-2 text-xs")}
          onClick={onReview}
        >
          {dense
            ? t("simulation.readiness.openScenario")
            : t("simulation.readiness.reviewAssumptions")}
          <ArrowRight aria-hidden className="size-3.5" />
        </Button>
      )}
    </div>
  );
}

/** Le domande che i disaccordi fra le fonti aprono, al massimo cinque. */
const MAX_CONFLICTS = 5;

function SourceConflicts({ conflicts }: { conflicts: SourceConflict[] }): React.JSX.Element {
  const { t, i18n } = useTranslation("process");
  const lang = i18n.language.startsWith("it") ? "it" : "en";
  const shown = conflicts.slice(0, MAX_CONFLICTS);
  const label = (source: SourceConflict["shortest"]) => (source.kind === "panel" ? t("simulation.sourceConflicts.panel") : `«${source.label}»`);
  return (
    <div className="grid gap-1.5 rounded-md border border-[var(--state-warning-border)] bg-[var(--state-warning-surface)] p-2.5" data-readiness-conflicts>
      <p className="flex items-center gap-1.5 text-micro font-medium text-foreground">
        <AlertTriangle aria-hidden className="size-3.5 shrink-0 text-[var(--state-warning-text)]" />
        {t("simulation.sourceConflicts.title")}
      </p>
      <p className="text-micro leading-snug text-muted-foreground">{t("simulation.sourceConflicts.hint")}</p>
      <ul className="grid gap-1">
        {shown.map((conflict) => (
          <li key={conflict.elementId} className="text-micro leading-snug text-foreground" data-conflict={conflict.elementId}>
            {t("simulation.sourceConflicts.question", {
              name: conflict.name,
              shortLabel: label(conflict.shortest),
              short: formatParameterDuration(conflict.shortest.seconds, lang),
              longLabel: label(conflict.longest),
              long: formatParameterDuration(conflict.longest.seconds, lang),
            })}
          </li>
        ))}
      </ul>
      {conflicts.length > shown.length && (
        <p className="text-micro text-muted-foreground">{t("simulation.sourceConflicts.more", { count: conflicts.length - shown.length })}</p>
      )}
    </div>
  );
}

function FactList({ title, items }: { title: string; items: string[] }): React.JSX.Element {
  return (
    <div className="grid gap-1">
      <p className="eyebrow">{title}</p>
      <ul className="grid gap-1">
        {items.map((item) => (
          <li
            key={item}
            className="flex items-start gap-1.5 text-micro leading-snug text-muted-foreground"
          >
            <span
              aria-hidden
              className="mt-1 size-1 shrink-0 rounded-full bg-muted-foreground/60"
            />
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}
