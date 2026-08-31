import React from "react";
import { useTranslation } from "react-i18next";
import { ArrowRight, Info } from "lucide-react";

import { Meter, type MeterTone } from "@/components/data";
import { StatusIndicator, type StatusTone } from "@/components/status";
import { Button } from "@/ui/button";
import { cn } from "@/lib/utils";

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

type ReadinessSummaryProps = {
  confidence: InputConfidence;
  provenance: ScenarioProvenance | null;
  /** Compact form for the Panoramica rail. */
  dense?: boolean;
  /** Deep-link to the full scenario builder / low-confidence fields. */
  onReview?: () => void;
  className?: string;
};

export function ReadinessSummary({
  confidence,
  provenance,
  dense = false,
  onReview,
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
        !dense && "rounded-lg border border-border bg-card p-4",
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
        <p className="flex items-start gap-2 rounded-md border border-border bg-muted/40 px-2.5 py-2 text-[11px] leading-snug text-muted-foreground">
          <Info aria-hidden className="mt-0.5 size-3.5 shrink-0" />
          {t("simulation.readiness.noDiscovery")}
        </p>
      )}

      {(confidence.hasDiscovery || !dense) && (
      <ul className="grid gap-2">
        {readiness.rows.map((row) => (
          <li key={row.key} className="grid gap-1">
            <div className="flex items-center justify-between gap-2 text-[11px]">
              <span className="font-medium text-foreground">
                {t(`simulation.readiness.row.${row.key}`)}
              </span>
              <span className="flex shrink-0 items-center gap-2">
                {!dense && row.flagged > 0 && (
                  <span className="text-[var(--amber-700)]">
                    {t("simulation.readiness.flagged", { count: row.flagged })}
                  </span>
                )}
                <span className="tabular-nums text-muted-foreground">{row.pct}%</span>
              </span>
            </div>
            <Meter value={row.pct} tone={METER_TONE[row.confidence]} showValue={false} height={4} />
          </li>
        ))}
      </ul>
      )}

      {!dense && openGatewayQuestions > 0 && (
        <p className="text-[11px] text-[var(--amber-700)]">
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

function FactList({ title, items }: { title: string; items: string[] }): React.JSX.Element {
  return (
    <div className="grid gap-1">
      <p className="eyebrow">{title}</p>
      <ul className="grid gap-1">
        {items.map((item) => (
          <li
            key={item}
            className="flex items-start gap-1.5 text-[11px] leading-snug text-muted-foreground"
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
