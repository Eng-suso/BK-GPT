import { formatProbability, type ReplicationKpi } from "./replications";
import { scenarioValue, WORKSPACE_KPIS, type ScenarioDelta, type ScenarioRuns } from "./scenarioWorkspace";
import type { Tornado } from "./sensitivity";
import { formatCurrency, formatDuration } from "./simulationResults";
import type { Confidence, InputConfidence } from "./simulationProvenance";
import type { SourceConflict } from "./sourceConflicts";

/**
 * SIM-27: il decision record di un'alternativa, da consegnare al cliente.
 *
 * Un solo documento HTML, senza dipendenze, che si apre in qualsiasi browser e
 * si stampa in PDF: cosa cambia rispetto all'AS-IS, i risultati con i loro
 * intervalli, le ipotesi con origine e confidenza, la sensitivita' e i rischi.
 * Tutto quello che c'e' qui viene dai run e dallo scenario: niente si inventa,
 * e cio' che manca si dice.
 */

type T = (key: string, options?: Record<string, unknown>) => string;

export type DecisionRecordInput = {
  processName: string;
  generatedAt: Date;
  seed: number | null;
  asIs: { name: string; results: ScenarioRuns };
  alternative: { name: string; results: ScenarioRuns; changes: string[] };
  deltas: { kpis: Record<ReplicationKpi, ScenarioDelta | null>; paired: boolean | null; mismatch: boolean };
  comparisons: number;
  readiness: InputConfidence["readiness"];
  /** Le ipotesi a confidenza bassa o media, con il nome dell'elemento. */
  uncertain: { name: string; confidence: Confidence; origin: string }[];
  conflicts: SourceConflict[];
  /** Lo studio di sensitivita' del run dell'alternativa, se c'e'. */
  tornado: Tornado | null;
};

const escape = (value: string) =>
  value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");

function formatters(t: T, lang: "it" | "en"): Record<ReplicationKpi, (v: number) => string> {
  const number = (v: number) => v.toLocaleString(lang === "it" ? "it-IT" : "en-US", { maximumFractionDigits: 2 });
  return {
    cycle: (v) => formatDuration(v, lang),
    waiting: (v) => formatDuration(v, lang),
    costPerCase: (v) => formatCurrency(v, lang),
    throughput: (v) => t("simulation.results.replicationPerHour", { value: number(v) }),
  };
}

function valueText(results: ScenarioRuns, kpi: ReplicationKpi, t: T, format: (v: number) => string): string {
  const value = scenarioValue(results, kpi);
  if (!value) return t("simulation.scenarios.workspace.notRun");
  return value.interval
    ? t("simulation.results.replicationValue", { mean: format(value.interval.mean), half: format(value.interval.half) })
    : format(value.mean);
}

function deltaText(delta: ScenarioDelta | null, t: T, lang: "it" | "en", format: (v: number) => string): string {
  if (!delta) return "—";
  const signed = (v: number) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${format(Math.abs(v))}`;
  if (delta.kind === "single") {
    return `${t("simulation.scenarios.workspace.deltaSingle", { delta: signed(delta.delta) })} · ${t("simulation.decisionRecord.noInterval")}`;
  }
  return [
    t("simulation.scenarios.workspace.deltaInterval", { delta: signed(delta.value.delta), half: format(delta.value.half) }),
    t(`simulation.scenarios.workspace.verdict.${delta.value.verdict}`),
    t("simulation.scenarios.workspace.probBetter", { value: formatProbability(delta.value.probBetter, lang) }),
  ].join(" · ");
}

const list = (items: string[]) => (items.length ? `<ul>${items.map((item) => `<li>${escape(item)}</li>`).join("")}</ul>` : "");

export function decisionRecordHtml(input: DecisionRecordInput, t: T, lang: "it" | "en"): string {
  const format = formatters(t, lang);
  const k = (key: string, options?: Record<string, unknown>) => t(`simulation.decisionRecord.${key}`, options);
  const date = input.generatedAt.toLocaleString(lang === "it" ? "it-IT" : "en-US", { dateStyle: "long", timeStyle: "short" });
  const runIds = (results: ScenarioRuns) => results.completed.map((r) => `#${r.id}`).join(", ") || "—";

  const resultsRows = WORKSPACE_KPIS.map((kpi) => `<tr><th scope="row">${escape(t(`simulation.results.replicationKpi.${kpi}`))}</th>`
    + `<td>${escape(valueText(input.asIs.results, kpi, t, format[kpi]))}</td>`
    + `<td>${escape(valueText(input.alternative.results, kpi, t, format[kpi]))}</td>`
    + `<td>${escape(input.deltas.mismatch ? k("mismatch") : deltaText(input.deltas.kpis[kpi], t, lang, format[kpi]))}</td></tr>`).join("");

  const method = input.deltas.mismatch
    ? k("mismatch")
    : input.deltas.paired === null
      ? k("methodSingle")
      : [t(`simulation.scenarios.workspace.method.${input.deltas.paired ? "paired" : "independent"}`),
        input.comparisons > 1 ? t("simulation.scenarios.workspace.method.bonferroni", { count: input.comparisons }) : ""].filter(Boolean).join(" ");

  const readinessRows = input.readiness.rows.map((row) => `<tr><th scope="row">${escape(t(`simulation.readiness.row.${row.key}`))}</th>`
    + `<td>${row.pct}%</td><td>${escape(t(`simulation.provenance.confidence.${row.confidence}`))}</td></tr>`).join("");
  const uncertain = input.uncertain.map((u) => k("uncertainItem", {
    name: u.name, origin: t(`simulation.provenance.source.${u.origin}`, { defaultValue: u.origin }),
    confidence: t(`simulation.provenance.confidence.${u.confidence}`),
  }));

  const tornado = input.tornado;
  const decisive = tornado ? tornado.rows.filter((r) => r.swing > 0 && !r.negligible) : [];
  const sensitivity = !tornado || tornado.center === undefined
    ? `<p>${escape(k("noSensitivity"))}</p>`
    : `<p>${escape(k("sensitivityIntro", { pct: Math.round(tornado.delta * 100), center: format.cycle(tornado.center) }))}</p>`
      + `<table><thead><tr><th scope="col">${escape(t("simulation.sensitivity.col.assumption"))}</th><th scope="col">−${Math.round(tornado.delta * 100)}%</th><th scope="col">+${Math.round(tornado.delta * 100)}%</th></tr></thead><tbody>`
      + tornado.rows.map((row) => `<tr><th scope="row">${escape(row.label)}${row.negligible ? ` <small>(${escape(t("simulation.sensitivity.negligible"))})</small>` : ""}</th>`
        + `<td>${row.low === undefined ? "—" : escape(format.cycle(row.low))}</td><td>${row.high === undefined ? "—" : escape(format.cycle(row.high))}</td></tr>`).join("")
      + "</tbody></table>";

  const risks: string[] = [];
  if (input.deltas.mismatch) risks.push(k("mismatch"));
  if (input.alternative.results.status === "stale" || input.asIs.results.status === "stale") risks.push(k("riskStale"));
  if (input.deltas.paired === null && !input.deltas.mismatch) risks.push(k("riskSingle"));
  if (input.readiness.overall !== "high") risks.push(k("riskReadiness", { level: t(`simulation.provenance.confidence.${input.readiness.overall}`) }));
  for (const conflict of input.conflicts) {
    risks.push(t("simulation.sourceConflicts.question", {
      name: conflict.name,
      shortLabel: conflict.shortest.kind === "panel" ? t("simulation.sourceConflicts.panel") : `«${conflict.shortest.label}»`,
      short: format.cycle(conflict.shortest.seconds),
      longLabel: conflict.longest.kind === "panel" ? t("simulation.sourceConflicts.panel") : `«${conflict.longest.label}»`,
      long: format.cycle(conflict.longest.seconds),
    }));
  }
  for (const row of decisive) risks.push(t(`simulation.sensitivity.question.${row.kind}`, { label: row.label }));

  const title = k("title", { name: input.alternative.name });
  return `<!doctype html>
<html lang="${lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${escape(title)}</title>
<style>
  body { font: 14px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif; color: #16202c; background: #fff; max-width: 860px; margin: 0 auto; padding: 32px 24px 48px; }
  h1 { font-size: 24px; margin: 0 0 4px; } h2 { font-size: 17px; margin: 28px 0 8px; padding-bottom: 4px; border-bottom: 1px solid #d9dfe7; }
  .meta { color: #5a6676; font-size: 12.5px; margin: 0; }
  table { border-collapse: collapse; width: 100%; font-size: 13.5px; } th, td { text-align: left; vertical-align: top; padding: 6px 8px; border-bottom: 1px solid #d9dfe7; }
  thead th { font-size: 12px; text-transform: uppercase; letter-spacing: .04em; color: #5a6676; } small { color: #5a6676; }
  ul { padding-left: 20px; } li { margin: 3px 0; } .note { color: #5a6676; font-size: 12.5px; }
  @media print { body { padding: 0; } h2 { break-after: avoid; } table, li { break-inside: avoid; } }
</style>
</head>
<body>
<h1>${escape(title)}</h1>
<p class="meta">${escape(k("meta", { process: input.processName, date, seed: input.seed ?? "—" }))}</p>
<p class="meta">${escape(k("runs", { asIs: input.asIs.name, asIsRuns: runIds(input.asIs.results), alternative: input.alternative.name, alternativeRuns: runIds(input.alternative.results) }))}</p>

<h2>${escape(k("changesTitle"))}</h2>
${input.alternative.changes.length ? list(input.alternative.changes) : `<p>${escape(k("noChanges"))}</p>`}

<h2>${escape(k("resultsTitle"))}</h2>
<table><thead><tr><th scope="col">${escape(k("kpi"))}</th><th scope="col">${escape(input.asIs.name)}</th><th scope="col">${escape(input.alternative.name)}</th><th scope="col">${escape(k("delta"))}</th></tr></thead>
<tbody>${resultsRows}</tbody></table>
<p class="note">${escape(method)}</p>

<h2>${escape(k("assumptionsTitle"))}</h2>
<table><thead><tr><th scope="col">${escape(k("family"))}</th><th scope="col">${escape(k("readiness"))}</th><th scope="col">${escape(k("confidence"))}</th></tr></thead>
<tbody>${readinessRows}</tbody></table>
<p class="note">${escape(k("overall", { level: t(`simulation.provenance.confidence.${input.readiness.overall}`) }))}</p>
${uncertain.length ? `<p>${escape(k("uncertainTitle"))}</p>${list(uncertain)}` : `<p>${escape(k("noUncertain"))}</p>`}

<h2>${escape(k("sensitivityTitle"))}</h2>
${sensitivity}

<h2>${escape(k("risksTitle"))}</h2>
${risks.length ? list(risks) : `<p>${escape(k("noRisks"))}</p>`}

<p class="note">${escape(k("footer"))}</p>
</body>
</html>
`;
}
