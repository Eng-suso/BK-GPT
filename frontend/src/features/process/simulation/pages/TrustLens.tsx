import React from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { Button } from "@/ui/button";
import { cn } from "@/lib/utils";

import type { NodeDecoration } from "../canvas/SimulationCanvas";
import { compareRealToSimulated, latestMappedLog, signedPercent } from "../eventlog/realVsSimulated";
import { useEventLogAnalysis, useEventLogs } from "../eventlog/useEventLogImport";
import { fetchScenarioTemplate } from "../simulationApi";
import type { SimulationRun, SimulationSummary } from "../simulationTypes";
import { useScenarioProvenance } from "../useInputConfidence";
import { useSimulationSection } from "../useSimulationSection";
import { useRunModel } from "../studio/runModel";
import { TRUST_MARKER, trustCounts, trustMap, type TrustRow, type TrustStatus } from "../studio/trustMap";

const BADGE_TONE: Record<TrustStatus, NodeDecoration["badgeTone"]> = {
  calibrate: "danger", weak: "warning", toConfirm: "neutral", solid: "neutral", validated: "neutral",
};

/**
 * SIM-20: la lente "Affidabilita'" della heatmap. Ogni attivita' e decisione
 * del run con il suo parametro piu' debole (origine, confidenza, fonti) e lo
 * scarto dal log reale piu' recente, colorata sul BPMN.
 */
export function TrustLens({ run, selectedEl, onSelect, onDecorations }: {
  run: SimulationRun;
  selectedEl: string | null;
  onSelect: (id: string | null) => void;
  onDecorations?: (items: NodeDecoration[]) => void;
}): React.JSX.Element {
  const { t, i18n } = useTranslation("process");
  const lang = i18n.language?.startsWith("it") ? "it" : "en";
  const { processId, openPanel, perspective } = useSimulationSection();
  const model = useRunModel(run.id);
  const provenance = useScenarioProvenance(run.bpmn_model_id);
  const template = useQuery({
    queryKey: ["workspace", "simulation-template", run.bpmn_model_id],
    queryFn: () => fetchScenarioTemplate(run.bpmn_model_id, null),
    staleTime: 60_000,
  });
  const logs = useEventLogs(processId);
  const log = latestMappedLog(logs.data);
  const analysis = useEventLogAnalysis(log?.id ?? null, Boolean(log));
  const real = analysis.data?.summary;
  const summary = run.summary as SimulationSummary | null;

  const rows = React.useMemo<TrustRow[]>(() => {
    if (!model.data) return [];
    const gaps = real && summary ? compareRealToSimulated(real, summary).activities : [];
    return trustMap(model.data, provenance.data?.elements ?? [], template.data ?? null, gaps);
  }, [model.data, provenance.data, template.data, real, summary]);

  const statusLabel = React.useCallback((status: TrustStatus) => t(`simulation.trust.status.${status}`), [t]);
  const decorations = React.useMemo<NodeDecoration[]>(() => rows.map((row) => ({
    elementId: row.el,
    markers: [TRUST_MARKER[row.status]],
    badge: row.status === "calibrate" && row.gap != null ? signedPercent(row.gap, lang) : row.status === "weak" || row.status === "calibrate" ? statusLabel(row.status) : undefined,
    badgeTone: BADGE_TONE[row.status],
  })), [rows, lang, statusLabel]);
  React.useEffect(() => { onDecorations?.(decorations); }, [decorations, onDecorations]);

  if (model.isLoading) return <p className="sim-help px-2" role="status">{t("simulation.activityInspector.loading")}</p>;
  if (!model.data) return <p className="sim-help px-2">{t("simulation.trust.noModel")}</p>;

  const counts = trustCounts(rows);
  return (
    <div className="grid gap-3" data-sim-trust>
      <section aria-labelledby="sim-trust-title" className="grid gap-2 px-2">
        <h3 id="sim-trust-title" className="text-sm font-semibold text-foreground">{t("simulation.trust.title")}</h3>
        <p className="text-xs text-muted-foreground">{t("simulation.trust.hint")}</p>
        <ul className="flex flex-wrap gap-1.5" aria-label={t("simulation.trust.countsLabel")}>
          {counts.map(({ status, count }) => (
            <li key={status} className="sim-trust-chip" data-trust={status}>
              <span aria-hidden className="sim-trust-swatch" />
              {t("simulation.trust.count", { count, status: statusLabel(status) })}
            </li>
          ))}
        </ul>
        <p className="text-xs text-muted-foreground" role="status">
          {logs.isPending || (log && analysis.isPending) ? t("simulation.trust.logLoading")
            : log ? t("simulation.trust.logUsed", { name: log.name })
              : t("simulation.trust.noLog")}
        </p>
        {!log && !logs.isPending && perspective !== "operations" && openPanel && (
          <Button size="sm" variant="outline" className="justify-self-start" onClick={() => openPanel("eventLog")}>{t("simulation.eventLog.inspector.import")}</Button>
        )}
      </section>
      <ul className="grid gap-0.5" aria-label={t("simulation.trust.listLabel")}>
        {rows.map((row) => (
          <li key={row.el}>
            <button
              type="button"
              aria-pressed={row.el === selectedEl}
              onClick={() => onSelect(row.el === selectedEl ? null : row.el)}
              className={cn(
                "grid w-full grid-cols-[minmax(0,1fr)_auto] items-start gap-2 rounded-md px-2 py-1.5 text-left transition-colors",
                "hover:bg-muted focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--sim-info)]",
                row.el === selectedEl && "bg-muted",
              )}
              data-trust={row.status}
            >
              <span className="min-w-0">
                <span className="flex items-center gap-1.5">
                  <span aria-hidden className="sim-trust-swatch" />
                  <span className="truncate text-xs font-medium text-foreground" title={row.name}>{row.name}</span>
                </span>
                <span className="mt-0.5 block text-2xs text-muted-foreground">
                  {t("simulation.provenance.sourceLabel", { source: t(`simulation.provenance.source.${row.origin}`), confidence: t(`simulation.provenance.confidence.${row.confidence}`) })}
                  {" · "}{t("simulation.trust.sources", { count: row.sources })}
                  {row.gap != null && <>{" · "}{t("simulation.trust.gap", { gap: signedPercent(row.gap, lang) })}</>}
                </span>
              </span>
              <span className="shrink-0 text-2xs font-medium text-foreground">{statusLabel(row.status)}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
