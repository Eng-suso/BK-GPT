import React from "react";

import { EmptyState } from "@/components/feedback";
import { Skeleton } from "@/ui/skeleton";
import { useTranslation } from "react-i18next";

import { SimulationConfigRail } from "../SimulationConfigRail";
import { ReadinessSummary } from "../ReadinessSummary";
import { useScenarioLab } from "../useScenarioLab";

/**
 * Scenario builder — the assumptions-review surface. Every simulable element
 * shows where its structure came from (discovery vs. inference) and how far to
 * trust the parameter set for it, rolled up into a Simulation Readiness score.
 */
export function ScenarioBuilderPage(): React.JSX.Element {
  const { t } = useTranslation("process");
  const lab = useScenarioLab();
  const {
    bpmnXml,
    template,
    templateLoading,
    draft,
    updateDraft,
    provenance,
    confidence,
    isRunning,
    error,
    handleRun,
  } = lab;

  const [focusEl, setFocusEl] = React.useState<string | null>(null);
  const lowCursor = React.useRef(0);

  const reviewLowest = React.useCallback(() => {
    const ids = confidence.readiness.lowConfidenceElementIds;
    if (ids.length === 0) return;
    const next = ids[lowCursor.current % ids.length];
    lowCursor.current += 1;
    setFocusEl(next);
  }, [confidence.readiness.lowConfidenceElementIds]);

  if (bpmnXml === null && !templateLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <EmptyState title={t("simulation.diagram.noModel")} />
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 lg:flex-row">
      <div className="min-w-0 flex-1 overflow-y-auto pb-4">
        <header className="mb-4">
          <h2 className="text-lg font-semibold tracking-[-0.01em] text-foreground">
            {t("simulation.scenario.pageTitle")}
          </h2>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {t("simulation.scenario.pageSubtitle")}
          </p>
        </header>

        {templateLoading ? (
          <div className="grid gap-3">
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-40 w-full" />
            <Skeleton className="h-40 w-full" />
          </div>
        ) : (
          <SimulationConfigRail
            embedded
            template={template}
            templateLoading={templateLoading}
            draft={draft}
            onDraftChange={updateDraft}
            isRunning={isRunning}
            error={error}
            onRun={() => void handleRun()}
            focusElementId={focusEl}
            provenance={confidence}
          />
        )}
      </div>

      <aside className="w-full shrink-0 lg:w-[320px]">
        <div className="lg:sticky lg:top-0">
          <ReadinessSummary
            confidence={confidence}
            provenance={provenance}
            onReview={
              confidence.readiness.lowConfidenceElementIds.length > 0
                ? reviewLowest
                : undefined
            }
          />
        </div>
      </aside>
    </div>
  );
}
