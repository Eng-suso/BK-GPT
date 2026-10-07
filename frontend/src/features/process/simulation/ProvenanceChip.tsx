import React from "react";
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

import type { Confidence, FieldProvenance } from "./simulationProvenance";

// Evidence tokens (semantic.css): confirmed, partial, missing — one per confidence.
const DOT: Record<Confidence, string> = {
  high: "bg-[var(--domain-evidence-confirmed-icon)]",
  medium: "bg-[var(--domain-evidence-partial-icon)]",
  low: "bg-transparent ring-1 ring-inset ring-[var(--domain-evidence-missing-border)]",
};

type ProvenanceChipProps = {
  field: FieldProvenance;
  /** Extra note already rendered elsewhere? hide the inline "N to validate". */
  hideNote?: boolean;
  className?: string;
};

/** Tooltip text: discovery evidence, else the sources, else why there is none. */
export function provenanceTip(
  field: FieldProvenance,
  t: (key: string, options?: Record<string, unknown>) => string,
): string {
  if (field.evidence && field.evidence.length > 0) {
    return `${t("simulation.provenance.evidenceTitle")}: ${field.evidence.join(" · ")}`;
  }
  if (field.sources && field.sources.length > 0) {
    const refs = field.sources.map(
      (ref) => `${t(`simulation.provenance.sourceKind.${ref.kind}`)} ${ref.label ?? ref.id}`,
    );
    return `${t("simulation.provenance.sourcesTitle")}: ${refs.join(" · ")}`;
  }
  return field.origin === "estimated"
    ? t("simulation.provenance.aiInferredHint")
    : t("simulation.provenance.noEvidence");
}

/**
 * Inline badge: a confidence dot + the origin word, on the Simulation IR's
 * five-level scale. The `title` carries the evidence or the sources (or why
 * there are none) so hovering explains the score.
 */
export function ProvenanceChip({
  field,
  hideNote,
  className,
}: ProvenanceChipProps): React.JSX.Element {
  const { t } = useTranslation("process");

  const source = t(`simulation.provenance.source.${field.origin}`);
  const confidence = t(`simulation.provenance.confidence.${field.confidence}`);

  const openQuestions =
    !hideNote && field.note ? Number(field.note) : 0;

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 text-[11px] leading-none text-muted-foreground",
        className,
      )}
      title={`${t("simulation.provenance.sourceLabel", { source, confidence })} — ${provenanceTip(field, t)}`}
    >
      <span aria-hidden className={cn("size-1.5 shrink-0 rounded-full", DOT[field.confidence])} />
      <span className="font-medium text-foreground/80">{source}</span>
      {openQuestions > 0 && (
        <span className="text-[var(--domain-evidence-partial-text)]">
          · {t("simulation.provenance.openQuestions", { count: openQuestions })}
        </span>
      )}
    </span>
  );
}
