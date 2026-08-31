/**
 * Turns the raw Prosimos statistics payload (see backend prosimos_adapter) into
 * a small, typed view model a non-technical consultant can read.
 */

export type ResourceLoad = {
  id: string;
  name: string;
  pool: string;
  utilizationPct: number;
  tasksAllocated: number;
};

export type TaskStat = {
  name: string;
  /** Matched BPMN element id (by name), when a model was provided. */
  elementId: string | null;
  volume: number;
  avgWaitingSec: number;
  avgProcessingSec: number;
  avgCycleSec: number;
  avgCost: number;
  totalCost: number;
  /** avgWaitingSec / avgCycleSec, 0–1 */
  waitingShare: number;
};

export type SimulationInsights = {
  hasData: boolean;
  casesCompleted: number;
  avgCycleSec: number;
  avgProcessingSec: number;
  avgWaitingSec: number;
  /** share of cycle time spent waiting, 0–1 */
  waitingShare: number;
  totalCost: number;
  avgCostPerCase: number;
  resources: ResourceLoad[];
  tasks: TaskStat[];
  bottleneck: TaskStat | null;
  /** BPMN element id of the bottleneck task, when matched. */
  bottleneckElementId: string | null;
  files: string[];
};

const ACTIVITY_LOCAL_NAMES = new Set([
  "task",
  "userTask",
  "serviceTask",
  "scriptTask",
  "businessRuleTask",
  "manualTask",
  "sendTask",
  "receiveTask",
  "callActivity",
  "subProcess",
]);

/** id -> name for every activity in the BPMN (browser DOMParser). */
export function bpmnActivityNames(bpmnXml: string | null | undefined): Map<string, string> {
  const map = new Map<string, string>();
  if (!bpmnXml || typeof DOMParser === "undefined") return map;
  let doc: Document;
  try {
    doc = new DOMParser().parseFromString(bpmnXml, "application/xml");
  } catch {
    return map;
  }
  if (doc.getElementsByTagName("parsererror").length > 0) return map;

  const walk = (node: Element) => {
    const local = node.localName;
    const id = node.getAttribute("id");
    if (id && ACTIVITY_LOCAL_NAMES.has(local)) {
      map.set(id, node.getAttribute("name") || id);
    }
    for (const child of Array.from(node.children)) walk(child);
  };
  const root = doc.documentElement;
  if (root) walk(root);
  return map;
}

function invert(map: Map<string, string>): Map<string, string> {
  // name -> id; first occurrence wins (duplicate names can't be disambiguated).
  const out = new Map<string, string>();
  for (const [id, name] of map) if (!out.has(name)) out.set(name, id);
  return out;
}

function toNum(value: unknown): number {
  if (typeof value === "number") return Number.isFinite(value) ? value : 0;
  if (typeof value === "string") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
}

function toStr(value: unknown, fallback = ""): string {
  return typeof value === "string" && value.length > 0 ? value : fallback;
}

/** Prosimos double/triple json-encodes some sections; decode defensively. */
function coerceRecords(value: unknown): Array<Record<string, unknown>> {
  let current = value;
  for (let i = 0; i < 4 && typeof current === "string"; i += 1) {
    try {
      current = JSON.parse(current) as unknown;
    } catch {
      break;
    }
  }
  if (!Array.isArray(current)) return [];
  return current.filter(
    (row): row is Record<string, unknown> =>
      typeof row === "object" && row !== null,
  );
}

function overallAverage(
  rows: Array<Record<string, unknown>>,
  kpi: string,
): { average: number; occurrences: number } {
  const row = rows.find((entry) => toStr(entry.KPI) === kpi);
  return {
    average: toNum(row?.Average),
    occurrences: toNum(row?.["Trace Ocurrences"]),
  };
}

export function readSimulationInsights(
  result: Record<string, unknown> | null | undefined,
  options: { bpmnXml?: string | null } = {},
): SimulationInsights {
  const empty: SimulationInsights = {
    hasData: false,
    casesCompleted: 0,
    avgCycleSec: 0,
    avgProcessingSec: 0,
    avgWaitingSec: 0,
    waitingShare: 0,
    totalCost: 0,
    avgCostPerCase: 0,
    resources: [],
    tasks: [],
    bottleneck: null,
    bottleneckElementId: null,
    files: [],
  };
  if (!result || typeof result !== "object") return empty;

  const nameToId = invert(bpmnActivityNames(options.bpmnXml));

  const overall = coerceRecords(result.OverallScenarioStatistics);
  const taskRows = coerceRecords(result.IndividualTaskStatistics);
  const resourceRows = coerceRecords(result.ResourceUtilization);

  if (overall.length === 0 && taskRows.length === 0 && resourceRows.length === 0) {
    return empty;
  }

  const cycle = overallAverage(overall, "cycle_time");
  const processing = overallAverage(overall, "processing_time");
  const waiting = overallAverage(overall, "waiting_time");

  const casesCompleted =
    cycle.occurrences ||
    taskRows.reduce((max, row) => Math.max(max, toNum(row.Count)), 0);

  const tasks: TaskStat[] = taskRows.map((row) => {
    const avgWaitingSec = toNum(row["Avg Waiting Time"]);
    const avgCycleSec = toNum(row["Avg Cycle Time"]);
    const name = toStr(row.Name, "—");
    return {
      name,
      elementId: nameToId.get(name) ?? null,
      volume: toNum(row.Count),
      avgWaitingSec,
      avgProcessingSec: toNum(row["Avg Processing Time"]),
      avgCycleSec,
      avgCost: toNum(row["Avg Cost"]),
      totalCost: toNum(row["Total Cost"]),
      waitingShare: avgCycleSec > 0 ? avgWaitingSec / avgCycleSec : 0,
    };
  });

  const resources: ResourceLoad[] = resourceRows.map((row, index) => ({
    id: toStr(row["Resource ID"], `resource-${index}`),
    name: toStr(row["Resource name"], toStr(row["Resource ID"], "—")),
    pool: toStr(row["Pool name"]),
    utilizationPct: Math.round(toNum(row["Utilization Ratio"]) * 100),
    tasksAllocated: toNum(row["Tasks Allocated"]),
  }));

  const totalCost = tasks.reduce((sum, task) => sum + task.totalCost, 0);

  const bottleneck =
    tasks.length > 0
      ? tasks.reduce((worst, task) =>
          task.avgWaitingSec > worst.avgWaitingSec ? task : worst,
        )
      : null;

  const files = [result.StatsFilename, result.LogsFilename]
    .filter((name): name is string => typeof name === "string" && name.length > 0);

  const realBottleneck = bottleneck && bottleneck.avgWaitingSec > 0 ? bottleneck : null;

  return {
    hasData: true,
    casesCompleted,
    avgCycleSec: cycle.average,
    avgProcessingSec: processing.average,
    avgWaitingSec: waiting.average,
    waitingShare: cycle.average > 0 ? waiting.average / cycle.average : 0,
    totalCost,
    avgCostPerCase: casesCompleted > 0 ? totalCost / casesCompleted : 0,
    resources,
    tasks,
    bottleneck: realBottleneck,
    bottleneckElementId: realBottleneck?.elementId ?? null,
    files,
  };
}

const DURATION_UNITS: Record<"it" | "en", { d: string; h: string; m: string; s: string }> = {
  it: { d: "g", h: "h", m: "min", s: "s" },
  en: { d: "d", h: "h", m: "min", s: "s" },
};

/** Compact wall-clock duration, two largest non-zero units (e.g. "2g 21h"). */
export function formatDuration(totalSeconds: number, lang: "it" | "en" = "it"): string {
  const u = DURATION_UNITS[lang] ?? DURATION_UNITS.it;
  const seconds = Math.max(0, Math.round(totalSeconds));
  if (seconds < 60) return `${seconds} ${u.s}`;

  const days = Math.floor(seconds / 86_400);
  const hours = Math.floor((seconds % 86_400) / 3_600);
  const minutes = Math.floor((seconds % 3_600) / 60);

  if (days > 0) return hours > 0 ? `${days}${u.d} ${hours}${u.h}` : `${days}${u.d}`;
  if (hours > 0) return minutes > 0 ? `${hours}${u.h} ${minutes} ${u.m}` : `${hours}${u.h}`;
  return `${minutes} ${u.m}`;
}

/** Single largest unit only — for chart axes ("3g", "20h", "45min"). */
export function formatDurationShort(
  totalSeconds: number,
  lang: "it" | "en" = "it",
): string {
  const u = DURATION_UNITS[lang] ?? DURATION_UNITS.it;
  const seconds = Math.max(0, Math.round(totalSeconds));
  if (seconds < 60) return `${seconds}${u.s}`;
  const days = Math.floor(seconds / 86_400);
  if (days > 0) return `${days}${u.d}`;
  const hours = Math.floor(seconds / 3_600);
  if (hours > 0) return `${hours}${u.h}`;
  return `${Math.floor(seconds / 60)}${u.m}`;
}

/** Compact currency for chart axes: "€3.2k" past a thousand. */
export function formatCurrencyShort(
  value: number,
  lang: "it" | "en" = "it",
): string {
  const v = Number.isFinite(value) ? value : 0;
  const sym = lang === "it" ? "€" : "€";
  if (Math.abs(v) >= 1000) return `${sym}${(v / 1000).toFixed(1)}k`;
  return `${sym}${Math.round(v)}`;
}

export function formatCurrency(value: number, lang: "it" | "en" = "it"): string {
  return new Intl.NumberFormat(lang === "it" ? "it-IT" : "en-US", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: value >= 1000 ? 0 : 2,
  }).format(Number.isFinite(value) ? value : 0);
}

export function formatPercent(ratio: number): string {
  return `${Math.round((Number.isFinite(ratio) ? ratio : 0) * 100)}%`;
}

export function formatCount(value: number, lang: "it" | "en" = "it"): string {
  return new Intl.NumberFormat(lang === "it" ? "it-IT" : "en-US").format(
    Math.round(Number.isFinite(value) ? value : 0),
  );
}

// --- diagram overlay policy -------------------------------------------------

/** 0–4 heat bucket by share of the worst waiting time (0 = coolest). */
export function heatBucket(waitSec: number, maxWaitSec: number): 0 | 1 | 2 | 3 | 4 {
  if (maxWaitSec <= 0 || waitSec <= 0) return 0;
  const ratio = Math.min(1, waitSec / maxWaitSec);
  return Math.min(4, Math.floor(ratio * 5)) as 0 | 1 | 2 | 3 | 4;
}

/**
 * The element ids that earn a text badge on the diagram: the bottleneck plus
 * the next worst-waiting tasks, up to `limit`. Everything else gets a heat
 * tint only, so a busy model stays readable.
 */
export function topBottleneckElementIds(
  insights: SimulationInsights,
  limit = 4,
): string[] {
  return [...insights.tasks]
    .filter((task) => task.elementId && task.avgWaitingSec > 0)
    .sort((a, b) => b.avgWaitingSec - a.avgWaitingSec)
    .slice(0, Math.max(1, limit))
    .map((task) => task.elementId as string);
}
