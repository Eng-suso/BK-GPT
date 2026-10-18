import React from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/ui/button";
import { cn } from "@/lib/utils";

import { buildTornado, studyMembers, type Tornado, type TornadoKpi, type TornadoRow } from "./sensitivity";
import { formatCurrency, formatDuration } from "./simulationResults";
import type { SimulationRun } from "./simulationTypes";
import { useSimulationSection } from "./useSimulationSection";

const KPIS: TornadoKpi[] = ["cycle", "costPerCase"];
/** Le domande per l'agente di discovery: solo le ipotesi che spostano davvero il risultato. */
const MAX_QUESTIONS = 3;

/**
 * SIM-25: il tornado dello studio di sensitivita' del run. Niente se il run
 * non fa parte di uno studio.
 */
export function SensitivityTornado({ run }: { run: SimulationRun }): React.JSX.Element | null {
  const { runs } = useSimulationSection();
  return <SensitivityPanel run={run} runs={runs ?? []} />;
}

export function SensitivityPanel({ run, runs }: { run: SimulationRun; runs: SimulationRun[] }): React.JSX.Element | null {
  const { t, i18n } = useTranslation("process");
  const lang = i18n.language?.startsWith("it") ? "it" : "en";
  const [kpi, setKpi] = React.useState<TornadoKpi>("cycle");
  const members = studyMembers(run, runs);
  const tornado = buildTornado(members, kpi);
  if (members.length === 0) return null;

  const pct = Math.round(tornado.delta * 100);
  const format = (v: number) => (kpi === "cycle" ? formatDuration(v, lang) : formatCurrency(v, lang));
  const ready = tornado.center !== undefined && tornado.rows.some((r) => r.low !== undefined && r.high !== undefined);
  const decisive = tornado.rows.filter((r) => r.swing > 0 && !r.negligible).slice(0, MAX_QUESTIONS);

  return (
    <section aria-labelledby="sim-sensitivity-title" className="mb-3 grid gap-2 rounded-md border border-border p-3" data-sim-sensitivity>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 id="sim-sensitivity-title" className="text-sm font-medium text-foreground">{t("simulation.sensitivity.title")}</h3>
          <p className="text-xs text-muted-foreground">{t("simulation.sensitivity.intro", { pct })}</p>
        </div>
        <div role="group" aria-label={t("simulation.sensitivity.kpiLabel")} className="flex shrink-0 gap-1">
          {KPIS.map((key) => (
            <Button key={key} type="button" size="sm" variant={kpi === key ? "secondary" : "ghost"} aria-pressed={kpi === key} onClick={() => setKpi(key)}>
              {t(`simulation.sensitivity.kpi.${key}`)}
            </Button>
          ))}
        </div>
      </div>
      <p className="text-xs text-muted-foreground" role="status">
        {t("simulation.sensitivity.progress", { done: tornado.completed, total: tornado.total })}
        {tornado.failed > 0 && ` ${t("simulation.sensitivity.failed", { count: tornado.failed })}`}
      </p>
      {ready ? (
        <>
          <TornadoChart tornado={tornado} pct={pct} format={format} />
          <p className="text-xs text-muted-foreground">{t("simulation.sensitivity.noiseHint")}</p>
          <div className="grid gap-1" data-sim-sensitivity-questions>
            <p className="eyebrow">{t("simulation.sensitivity.voiTitle")}</p>
            {decisive.length > 0 ? (
              <ol className="grid list-decimal gap-1 pl-5 text-xs text-foreground">
                {decisive.map((row) => <li key={row.key}>{t(`simulation.sensitivity.question.${row.kind}`, { label: row.label })}</li>)}
              </ol>
            ) : (
              <p className="text-xs text-muted-foreground">{t("simulation.sensitivity.voiNone", { pct })}</p>
            )}
          </div>
        </>
      ) : (
        <p className="text-xs text-muted-foreground">{t("simulation.sensitivity.waiting")}</p>
      )}
    </section>
  );
}

function TornadoChart({ tornado, pct, format }: { tornado: Tornado; pct: number; format: (v: number) => string }): React.JSX.Element {
  const { t } = useTranslation("process");
  const center = tornado.center ?? 0;
  const deviations = tornado.rows.flatMap((r) => [r.low, r.high]).filter((v): v is number => v !== undefined).map((v) => Math.abs(v - center));
  const scale = Math.max(...deviations, Number.EPSILON);

  return (
    <div className="grid gap-2">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
        <span>{t("simulation.sensitivity.center", { value: format(center) })}</span>
        <span className="flex items-center gap-1.5"><span aria-hidden className="size-2.5 rounded-sm" style={{ background: "var(--sim-tornado-low)" }} />{t("simulation.sensitivity.low", { pct })}</span>
        <span className="flex items-center gap-1.5"><span aria-hidden className="size-2.5 rounded-sm" style={{ background: "var(--sim-tornado-high)" }} />{t("simulation.sensitivity.high", { pct })}</span>
      </div>
      <table className="w-full table-fixed text-xs">
        <caption className="sr-only">{t("simulation.sensitivity.title")}</caption>
        <thead className="sr-only">
          <tr>
            <th scope="col">{t("simulation.sensitivity.col.assumption")}</th>
            <th scope="col">{t("simulation.sensitivity.col.effect")}</th>
            <th scope="col">{t("simulation.sensitivity.col.values")}</th>
          </tr>
        </thead>
        <tbody>
          {tornado.rows.map((row) => <TornadoBar key={row.key} row={row} center={center} scale={scale} pct={pct} format={format} />)}
        </tbody>
      </table>
    </div>
  );
}

function TornadoBar({ row, center, scale, pct, format }: { row: TornadoRow; center: number; scale: number; pct: number; format: (v: number) => string }): React.JSX.Element {
  const { t } = useTranslation("process");
  const pending = t("simulation.sensitivity.pendingValue");
  const values = t("simulation.sensitivity.rowValues", {
    pct,
    low: row.low !== undefined ? format(row.low) : pending,
    high: row.high !== undefined ? format(row.high) : pending,
  });
  const segment = (value: number | undefined, color: string) => {
    if (value === undefined) return null;
    const width = (Math.abs(value - center) / scale) * 50;
    const left = value < center ? 50 - width : 50;
    return <span aria-hidden className="absolute inset-y-0.5 rounded-sm" style={{ left: `${left}%`, width: `max(${width}%, 2px)`, background: color }} />;
  };
  return (
    <tr className="align-middle" data-sim-tornado-row={row.key}>
      <th scope="row" className="w-[34%] py-1 pr-2 text-left font-normal">
        <span className="block truncate text-foreground" title={row.label}>{row.label}</span>
        <span className="text-muted-foreground">{t(`simulation.sensitivity.kind.${row.kind}`)}</span>
      </th>
      <td className="py-1">
        <div className="relative h-4" title={values}>
          <span aria-hidden className="absolute inset-y-0 left-1/2 w-px bg-[var(--sim-chart-axis)]" />
          {segment(row.low, "var(--sim-tornado-low)")}
          {segment(row.high, "var(--sim-tornado-high)")}
        </div>
      </td>
      <td className={cn("w-[36%] py-1 pl-2 text-right tabular-nums", row.negligible ? "text-muted-foreground" : "text-foreground")}>
        {values}
        {row.negligible && <span className="block text-muted-foreground">{t("simulation.sensitivity.negligible")}</span>}
      </td>
    </tr>
  );
}
