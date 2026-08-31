import React from "react";
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

import type { Confidence, FieldProvenance } from "./simulationProvenance";

const DOT: Record<Confidence, string> = {
  high: "bg-[var(--color-status-success)]",
  medium: "bg-[var(--amber-600)]",
  low: "bg-transparent ring-1 ring-inset ring-muted-foreground/50",
};

type ProvenanceChipProps = {
  field: FieldProvenance;
  /** Extra note already rendered elsewhere? hide the inline "N to validate". */
  hideNote?: boolean;
  className?: string;
};

/**
 * Inline badge: a confidence dot + the source word. The `title` carries the
 * discovery evidence (or why there is none) so hovering explains the score.
 */
export function ProvenanceChip({
  field,
  hideNote,
  className,
}: ProvenanceChipProps): React.JSX.Element {
  const { t } = useTranslation("process");

  const source = t(`simulation.provenance.source.${field.source}`);
  const confidence = t(`simulation.provenance.confidence.${field.confidence}`);

  const tip =
    field.evidence && field.evidence.length > 0
      ? `${t("simulation.provenance.evidenceTitle")}: ${field.evidence.join(" · ")}`
      : field.source === "inferred" || field.source === "estimated"
        ? t("simulation.provenance.aiInferredHint")
        : t("simulation.provenance.noEvidence");

  const openQuestions =
    !hideNote && field.note ? Number(field.note) : 0;

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 text-[11px] leading-none text-muted-foreground",
        className,
      )}
      title={`${t("simulation.provenance.sourceLabel", { source, confidence })} — ${tip}`}
    >
      <span aria-hidden className={cn("size-1.5 shrink-0 rounded-full", DOT[field.confidence])} />
      <span className="font-medium text-foreground/80">{source}</span>
      {openQuestions > 0 && (
        <span className="text-[var(--amber-700)]">
          · {t("simulation.provenance.openQuestions", { count: openQuestions })}
        </span>
      )}
    </span>
  );
}
