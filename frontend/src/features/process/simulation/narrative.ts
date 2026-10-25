import type { ReplicationKpi } from "./replications";
import type { ScenarioDelta } from "./scenarioWorkspace";
import type { SimulationNarrativeRequest } from "./simulationTypes";

/**
 * SIM-24b: la richiesta per il testo del cliente, dalla stessa tabella del workspace.
 *
 * Il valore di ogni KPI parte gia' formattato, con il segno e l'intervallo: il
 * modello lo cita con un segnaposto e il backend ce lo rimette, cosi' nel testo
 * non entra nessun numero che i run non abbiano prodotto.
 */

type Verdict = SimulationNarrativeRequest["kpis"][number]["verdict"];

export function deltaVerdict(delta: ScenarioDelta): Verdict {
  return delta.kind === "interval" ? delta.value.verdict : delta.direction;
}

export function narrativeRequest(input: {
  language: "it" | "en";
  asIsName: string;
  scenarioName: string;
  kpis: ReplicationKpi[];
  deltas: Partial<Record<ReplicationKpi, ScenarioDelta | null>>;
  label: (kpi: ReplicationKpi) => string;
  value: (kpi: ReplicationKpi, delta: ScenarioDelta) => string;
  reading: string[];
  names: string[];
}): SimulationNarrativeRequest | null {
  const kpis = input.kpis.flatMap((kpi) => {
    const delta = input.deltas[kpi];
    return delta ? [{ label: input.label(kpi), value: input.value(kpi, delta), verdict: deltaVerdict(delta) }] : [];
  });
  // Senza nessuna differenza misurata non c'e' niente da raccontare.
  if (!kpis.length) return null;
  return {
    language: input.language,
    as_is_name: input.asIsName,
    scenario_name: input.scenarioName,
    kpis,
    reading: input.reading.slice(0, 6),
    names: [...new Set(input.names.filter(Boolean))].slice(0, 60),
  };
}
