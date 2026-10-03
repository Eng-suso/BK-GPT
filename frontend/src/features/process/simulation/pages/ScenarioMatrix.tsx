import React from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { kpiDeltas } from "../compareDeltas";
import type { SimulationRun } from "../simulationTypes";
import { formatCurrency, formatDuration, formatPercent } from "../simulationResults";
import { formatMetric } from "../dashboard/dashboardFormatting";
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell, TableCaption } from "@/ui/table";
import { Checkbox } from "@/ui/checkbox";
import { Button } from "@/ui/button";

export function ScenarioMatrix({ baseline, alternative, candidates }: { baseline: SimulationRun; alternative: SimulationRun; candidates: SimulationRun[] }): React.JSX.Element {
  const { t, i18n } = useTranslation("process");
  const [params, setParams] = useSearchParams();
  const lang = i18n.language.startsWith("it") ? "it" : "en";
  const extraIds = [...new Set((params.get("scenarios") ?? "").split(","))].filter(id => candidates.some(run => String(run.id) === id && run.id !== baseline.id && run.id !== alternative.id)).slice(0, 3);
  const alternatives = [alternative, ...extraIds.map(id => candidates.find(run => String(run.id) === id)!)];
  const rows = kpiDeltas(baseline.summary!, baseline.summary!);
  const deltas = alternatives.map(run => kpiDeltas(baseline.summary!, run.summary!));
  const format = (value: number, kind: string) => !Number.isFinite(value) ? "—" : kind === "duration" ? formatDuration(value, lang) : kind === "currency" ? formatCurrency(value, lang) : kind === "percent" ? `${Math.round(value)}%` : kind === "rate" ? formatMetric(value, "rate", lang) : String(Math.round(value));
  const toggle = (id: string) => {
    const next = new URLSearchParams(params);
    const ids = extraIds.includes(id) ? extraIds.filter(item => item !== id) : [...extraIds, id].slice(0, 3);
    if (ids.length) next.set("scenarios", ids.join(",")); else next.delete("scenarios");
    setParams(next, { replace: true });
  };
  return <details className="sim-multi-comparison">
    <summary>{t("simulation.decision.multiTitle")}</summary>
    <div className="sim-scenario-selection" role="group" aria-label={t("simulation.decision.chooseAlternatives")}>
      {candidates.filter(run => run.id !== baseline.id).map(run => <label key={run.id} className="ui-surface ui-surface-inset"><Checkbox aria-label={`${run.scenario_name} · #${run.id}`} checked={run.id === alternative.id || extraIds.includes(String(run.id))} disabled={run.id === alternative.id || (!extraIds.includes(String(run.id)) && extraIds.length >= 3)} onCheckedChange={() => toggle(String(run.id))} />{run.scenario_name} · #{run.id}</label>)}
    </div>
    {alternatives.some(run => run.bpmn_model_id !== baseline.bpmn_model_id) && <p className="sim-comparison-compatibility" role="status">{t("simulation.decision.modelMismatch")}</p>}
    <div className="sim-scenario-matrix ui-surface ui-surface-inset" tabIndex={0} role="region" aria-label={t("simulation.decision.matrix")}>
      <Table><TableCaption>{t("simulation.decision.matrixHint")}</TableCaption><TableHeader><TableRow><TableHead scope="col">{t("simulation.compare.metric")}</TableHead><TableHead scope="col">{baseline.scenario_name}<small>{t("simulation.decision.reference")} · #{baseline.id}</small></TableHead>{alternatives.map(run => <TableHead scope="col" key={run.id}>{run.scenario_name}<small>{t("simulation.decision.alternative")} · #{run.id}</small><Button size="sm" variant="ghost" onClick={() => { const next = new URLSearchParams(params); next.set("b", String(run.id)); next.set("compareMode", "b"); next.set("scenarios", alternatives.filter(item => item.id !== run.id).map(item => item.id).join(",")); setParams(next, { replace: true }); }}>{t("simulation.decision.inspect")}</Button></TableHead>)}</TableRow></TableHeader>
      <TableBody>{rows.map((row, index) => <TableRow key={row.key}><TableHead scope="row">{t(`simulation.compare.kpi.${row.labelKey}`)}</TableHead><TableCell><strong>{format(row.a, row.format)}</strong></TableCell>{alternatives.map((run, column) => { const delta = deltas[column][index]; return <TableCell key={run.id}><strong>{format(delta.b, delta.format)}</strong><span className={delta.direction === "better" ? "is-better" : delta.direction === "worse" ? "is-worse" : ""}>{delta.deltaPct == null ? "—" : `${delta.deltaPct > 0 ? "+" : delta.deltaPct < 0 ? "−" : ""}${formatPercent(Math.abs(delta.deltaPct))}`} · {t(delta.direction === "better" ? "simulation.compare.better" : delta.direction === "worse" ? "simulation.compare.worse" : "simulation.decision.unchanged")}</span></TableCell>; })}</TableRow>)}</TableBody></Table>
    </div>
  </details>;
}
