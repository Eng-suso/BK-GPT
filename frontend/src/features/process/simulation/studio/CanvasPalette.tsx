import React from "react";
import { useTranslation } from "react-i18next";
import { Activity, ChartArea, ChartBar, ChartColumn, ChartLine, ChartPie, CircleDot, Gauge, GripVertical, Hash, LayoutGrid, Table2, Type, Workflow, X } from "lucide-react";
import { Surface } from "@/ui/surface";
import { Button } from "@/ui/button";
import { KINDS } from "../dashboard/dashboardModel";

import { paletteMetrics as metrics, paletteAnalyses as analyses, PALETTE_DRAG_TYPE, type PaletteItem } from "./canvasPaletteModel";

const icons = { line: ChartLine, area: ChartArea, bar: ChartBar, column: ChartColumn, pie: ChartPie, donut: CircleDot, gauge: Gauge, radial: Activity, kpi: Hash, table: Table2, text: Type };

export function CanvasPalette({ onAdd, onClose, full }: { onAdd: (item: PaletteItem) => void; onClose: () => void; full: boolean }): React.JSX.Element {
  const { t } = useTranslation("process");
  const [category, setCategory] = React.useState<"analysis" | "charts" | "notes">("analysis");
  const root = React.useRef<HTMLElement>(null);
  React.useEffect(() => { root.current?.querySelector<HTMLButtonElement>("button")?.focus({ preventScroll: true }); }, []);
  const tile = (item: PaletteItem, title: string, hint: string, key: string) => {
    const Icon = icons[item.kind];
    return <Button key={key} variant="outline" type="button" className="sim-palette-item" disabled={full} draggable={!full} data-palette-kind={item.kind} data-palette-metric={item.metric} onClick={() => onAdd(item)} onDragStart={event => { event.dataTransfer.setData(PALETTE_DRAG_TYPE, JSON.stringify(item)); event.dataTransfer.effectAllowed = "copy"; }}>
      <span className={`sim-palette-icon ${item.note ? "is-note" : ""}`}><Icon aria-hidden className="size-5" /></span><span><strong>{title}</strong><small>{hint}</small></span><GripVertical aria-hidden className="sim-palette-grip size-4" />
    </Button>;
  };
  return <Surface asChild variant="chrome"><aside ref={root} className="sim-canvas-palette" aria-label={t("simulation.studio.libraryTitle")} onKeyDown={event => { if (event.key === "Escape") { event.preventDefault(); onClose(); } }}>
    <header><div><span className="sim-palette-brand"><Workflow aria-hidden className="size-3.5" />DeliR · Studio</span><h3>{t("simulation.studio.libraryTitle")}</h3></div><Button size="icon" variant="ghost" aria-label={t("simulation.authoring.closeLibrary")} onClick={onClose}><X aria-hidden className="size-4" /></Button></header>
    <p className="sim-palette-hint">{t("simulation.authoring.addHint")}</p>
    <div className="sim-palette-categories" role="group" aria-label={t("simulation.authoring.categories")}>{(["analysis", "charts", "notes"] as const).map(id => <Button variant={category === id ? "secondary" : "ghost"} size="sm" type="button" key={id} aria-pressed={category === id} onClick={() => setCategory(id)}>{t(`simulation.authoring.${id}`)}</Button>)}</div>
    <div className="sim-palette-content" tabIndex={0}>
      {category === "analysis" && <><h4>{t("simulation.authoring.metrics")}</h4>{metrics.map(metric => tile({ kind: "kpi", metric }, `KPI · ${t(`simulation.studio.metric.${metric}`)}`, t("simulation.studio.kindHint.kpi"), metric))}<h4>{t("simulation.authoring.readyAnalyses")}</h4>{analyses.map(item => tile(item, t(`simulation.studio.metric.${item.metric}`), t(`simulation.studio.kindHint.${item.kind}`), `analysis-${item.metric}`))}</>}
      {category === "charts" && <><h4><LayoutGrid aria-hidden className="size-3.5" />{t("simulation.authoring.visualizations")}</h4>{KINDS.filter(kind => kind !== "text").map(kind => tile({ kind }, t(`simulation.studio.kind.${kind}`), t(`simulation.studio.kindHint.${kind}`), kind))}</>}
      {category === "notes" && <><h4>{t("simulation.authoring.context")}</h4>{tile({ kind: "text", note: true }, t("simulation.authoring.note"), t("simulation.authoring.noteHint"), "note")}{tile({ kind: "text" }, t("simulation.studio.kind.text"), t("simulation.studio.kindHint.text"), "text")}</>}
    </div>
    <footer role="status">{t(full ? "simulation.authoring.full" : "simulation.authoring.libraryFooter")}</footer>
  </aside></Surface>;
}
