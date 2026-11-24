import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import "@/lib/i18n";
import { HttpError } from "@/lib/http";

import { SimulationSectionContext, type SimulationSectionValue } from "../useSimulationSection";

const http = vi.fn();

vi.mock("@/lib/http", async () => {
  const actual = await vi.importActual<typeof import("@/lib/http")>("@/lib/http");
  return { ...actual, http: (path: string, options?: unknown) => http(path, options) };
});

const { EventLogPanel } = await import("./EventLogPanel");

const SECTION = {
  projectId: "p2p",
  processId: "acquisti",
  process: { id: "acquisti", bpmnModelId: "acquisti-bpmn", name: "Acquisti" },
  runs: [],
} as unknown as SimulationSectionValue;

const COLUMNS = ["Ordine", "Attivita", "Fine", "Utente"];
const LOG = {
  id: "elog_1",
  process_id: "acquisti",
  name: "erp.csv",
  format: "csv",
  delimiter: ";",
  byte_size: 120,
  row_count: 3,
  columns: COLUMNS,
  status: "uploaded",
  mapping: null,
  template: null,
  created_at: "2026-10-07T10:00:00Z",
  mapped_at: null,
};
const PREVIEW = {
  format: "csv",
  delimiter: ";",
  columns: COLUMNS,
  row_count: 3,
  sample_rows: [["PO-1", "Ricevi richiesta", "2026-01-05T09:10:00", "anna"]],
};
const MAPPING = {
  case_id: ["Ordine"],
  activity: ["Attivita"],
  start: null,
  end: "Fine",
  enable: null,
  timestamp: null,
  lifecycle: null,
  resource: "Utente",
  role: null,
  cost: null,
  case_attributes: [],
  event_attributes: [],
  timestamps: { pattern: null, timezone: "Europe/Rome" },
  numbers: { decimal: ".", thousands: "" },
};
const ANALYSIS = {
  event_log: { ...LOG, status: "mapped", mapping: MAPPING, mapped_at: "2026-10-07T10:01:00Z" },
  quality: {
    rows_read: 3,
    rows_excluded: 1,
    events: 2,
    cases: 1,
    activities: 2,
    resources: 1,
    period_start: "2026-01-05T09:00:00+01:00",
    period_end: "2026-01-05T11:00:00+01:00",
    events_without_start: 2,
    issues: [{ code: "missing_case_id", message: "Righe senza identificativo del caso: escluse.", count: 1, rows: [4], excludes_rows: true }],
  },
  activities: {
    bpmn_version_id: 3,
    confirmed: false,
    matches: [
      { activity: "Ricevi richiesta", events: 1, element_id: "T1", reason: "same_name" },
      { activity: "Approva", events: 1, element_id: null, reason: "none" },
    ],
    unmatched_activities: ["Approva"],
    unobserved_elements: [{ element_id: "T2", name: "Approvazione ordine" }],
  },
  resources: {
    confirmed: false,
    matches: [{ resource: "anna", events: 2, model_resource_id: null, reason: "none" }],
    unmatched_resources: ["anna"],
    unobserved_model_resources: [{ resource_id: "lane-1", name: "Ufficio acquisti" }],
    events_without_resource: 0,
  },
  summary: {
    casesCompleted: 1,
    cycle: { avg: 7200, p50: 7200, p90: 7200 },
    waiting: { avg: 0 },
    processing: { avg: 7200 },
    throughputPerHour: 0.5,
    cost: null,
    timing: "complete_only",
  },
};
const MODEL = {
  resources: [{ id: "lane-1", name: "Ufficio acquisti", kind: "lane", bpmn_id: "Lane_1", task_ids: ["T1"] }],
  tasks: [
    { element_id: "T1", name: "Ricevi richiesta", type: "task" },
    { element_id: "T2", name: "Approvazione ordine", type: "task" },
  ],
  gateways: [],
};

function routes(overrides: Record<string, unknown> = {}) {
  http.mockImplementation(async (path: string, options?: { method?: string }) => {
    const method = options?.method ?? "GET";
    const key = `${method} ${path.split("?")[0]}`;
    if (key in overrides) return overrides[key];
    switch (key) {
      case "GET /v1/workspace/processes/acquisti/event-logs": return [LOG];
      case "GET /v1/workspace/event-logs/elog_1/preview": return PREVIEW;
      case "GET /v1/workspace/event-logs/elog_1/validation": return {
        referenceCases: 1, simulatedCases: [1], replications: 1, runIds: [7], basis: "first_observed_start_and_between_activities", initialActivities: ["T1"],
        kpis: Object.fromEntries(["cycle", "p50", "p90", "between", "processing", "throughput"].map((key) => [key, { real: 100, mean: 105, ci95Half: null, min: 105, max: 105, bias: 5, mae: 5 }])),
        distances: { cycleW1: { mean: 0, ci95Half: null, min: 0, max: 0 }, ngd: { mean: 0, ci95Half: null, min: 0, max: 0 } },
        pooledCycle: { p50: 1, p90: 1 },
        firstWaitSimulated: null, quality: { rowsExcluded: 0, eventsWithoutStart: 0 },
        provenance: { eventLogId: "elog_1", runs: [{ runId: 7, seed: 1, engine: "Prosimos", engineVersion: "1", startDate: "2026-11-23T00:00:00+00:00", warmupCases: 0 }] },
      };
      case "GET /v1/workspace/event-log-templates": return [];
      case "POST /v1/workspace/bpmn-models/acquisti-bpmn/simulation-template": return MODEL;
      case "POST /v1/workspace/event-logs/elog_1/mapping": return ANALYSIS;
      default: throw new Error(`unexpected ${key}`);
    }
  });
}

function renderPanel(section: SimulationSectionValue = SECTION, onDecorations?: (items: unknown) => void) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>
      <SimulationSectionContext.Provider value={section}>{children}</SimulationSectionContext.Provider>
    </QueryClientProvider>
  );
  return render(<EventLogPanel onDecorations={onDecorations} />, { wrapper });
}

const activityKpis = (el: string | null, name: string, wait: number, processing: number) => ({
  el, name, count: 4, wait: { avg: wait, p95: wait }, processing: { avg: processing, p95: processing },
});
const TIMED_ANALYSIS = {
  ...ANALYSIS,
  summary: {
    ...ANALYSIS.summary,
    cycle: { avg: 7200, p50: 7000, p90: 9000 },
    waiting: { avg: 1800 },
    processing: { avg: 5400 },
    timing: "start_and_end",
    firstEnableObserved: true,
    enablementObserved: true,
    byActivity: [activityKpis("T1", "Ricevi richiesta", 600, 1800), activityKpis(null, "Approva", 1200, 3600)],
  },
};
const RUN = {
  id: 7,
  scenario_name: "Baseline",
  status: "completed",
  created_at: "2026-10-07T12:00:00Z",
  summary: {
    casesCompleted: 200,
    cycle: { avg: 7560, p50: 7200, p90: 9900, p95: 11000 },
    waiting: { avg: 2000 },
    processing: { avg: 5560 },
    cost: { total: 400, perCase: 2 },
    throughputPerHour: 0.6,
    byActivity: [activityKpis("T1", "Ricevi richiesta", 700, 2700), activityKpis("T2", "Approvazione ordine", 900, 2860)],
  },
};

function calls(method: string, path: string) {
  return http.mock.calls.filter(([p, o]) => p.split("?")[0] === path && ((o as { method?: string } | undefined)?.method ?? "GET") === method);
}

afterEach(() => {
  http.mockReset();
});

describe("EventLogPanel", () => {
  it("uploads a file with automatic separator detection and opens the wizard", async () => {
    routes({
      "GET /v1/workspace/processes/acquisti/event-logs": [],
      "POST /v1/workspace/processes/acquisti/event-logs": { ...LOG, created: true, preview: PREVIEW },
    });
    const user = userEvent.setup();
    renderPanel();

    expect(await screen.findByText("Nessun event log")).toBeInTheDocument();
    await user.upload(screen.getByLabelText("File dell'event log"), new File(["a;b"], "erp.csv", { type: "text/csv" }));

    await waitFor(() => expect(calls("POST", "/v1/workspace/processes/acquisti/event-logs")).toHaveLength(1));
    const body = (calls("POST", "/v1/workspace/processes/acquisti/event-logs")[0][1] as { body: FormData }).body;
    expect(body.get("delimiter")).toBeNull();
    expect((body.get("file") as File).name).toBe("erp.csv");
  });

  it("maps the columns, applies the mapping and shows quality and KPIs", async () => {
    routes();
    const user = userEvent.setup();
    renderPanel();

    await user.click(await screen.findByRole("button", { name: /^erp\.csv/ }));
    expect(await screen.findByRole("region", { name: "Righe dell'event log" })).toHaveTextContent("PO-1");

    const caseId = screen.getByRole("group", { name: "Identificativo del caso" });
    expect(caseId).toHaveTextContent("Ordine");
    const activity = screen.getByRole("group", { name: "Attività" });
    expect(activity).toHaveTextContent("Attivita");
    expect(screen.getByLabelText("Fine (o completamento)")).toHaveValue("Fine");
    await user.click(screen.getByRole("button", { name: "Avanti" }));
    await user.click(screen.getByRole("button", { name: "Applica il mapping" }));

    await waitFor(() => expect(calls("POST", "/v1/workspace/event-logs/elog_1/mapping")).toHaveLength(1));
    const sent = (calls("POST", "/v1/workspace/event-logs/elog_1/mapping")[0][1] as { body: Record<string, unknown> }).body;
    expect(sent.mapping).toEqual(MAPPING);
    expect(sent.template_id).toBeUndefined();

    expect(await screen.findByText(/righe senza identificativo del caso/)).toBeInTheDocument();
    expect(screen.getByText(/solo i completamenti/)).toBeInTheDocument();
    expect(screen.getByText("Non nel log")).toBeInTheDocument();
  });

  it("does not apply an incomplete mapping and says what is missing", async () => {
    routes({ "GET /v1/workspace/processes/acquisti/event-logs": [{ ...LOG, columns: ["A", "B", "C", "D"] }] });
    const user = userEvent.setup();
    renderPanel();

    await user.click(await screen.findByRole("button", { name: /^erp\.csv/ }));
    await user.click(await screen.findByRole("button", { name: "Avanti" }));

    expect(screen.getByRole("button", { name: "Applica il mapping" })).toBeDisabled();
    expect(screen.getByText("la colonna dell'identificativo del caso")).toBeInTheDocument();
    expect(calls("POST", "/v1/workspace/event-logs/elog_1/mapping")).toHaveLength(0);
  });

  it("sends the activity and resource matches decided by the consultant", async () => {
    routes({
      "GET /v1/workspace/processes/acquisti/event-logs": [ANALYSIS.event_log],
      "GET /v1/workspace/event-logs/elog_1/analysis": ANALYSIS,
    });
    const user = userEvent.setup();
    renderPanel();

    await user.click(await screen.findByRole("button", { name: /^erp\.csv/ }));
    await user.click(await screen.findByRole("button", { name: /Attività$/ }));
    await user.selectOptions(await screen.findByLabelText("Elemento del BPMN per Approva"), "T2");
    await user.click(screen.getByRole("button", { name: "Conferma l'abbinamento" }));

    await waitFor(() => expect(calls("POST", "/v1/workspace/event-logs/elog_1/mapping")).toHaveLength(1));
    let sent = (calls("POST", "/v1/workspace/event-logs/elog_1/mapping")[0][1] as { body: Record<string, unknown> }).body;
    expect(sent.activity_matches).toEqual({ "Ricevi richiesta": "T1", Approva: "T2" });
    expect(sent.mapping).toEqual(MAPPING);

    await user.click(screen.getByRole("button", { name: /Risorse$/ }));
    await user.selectOptions(await screen.findByLabelText("Risorsa del modello per anna"), "lane-1");
    await user.click(screen.getByRole("button", { name: "Conferma l'abbinamento" }));

    await waitFor(() => expect(calls("POST", "/v1/workspace/event-logs/elog_1/mapping")).toHaveLength(2));
    sent = (calls("POST", "/v1/workspace/event-logs/elog_1/mapping")[1][1] as { body: Record<string, unknown> }).body;
    expect(sent.resource_matches).toEqual({ anna: "lane-1" });
  });

  it("compares the real log with a completed run and paints the gaps on the process", async () => {
    routes({
      "GET /v1/workspace/processes/acquisti/event-logs": [ANALYSIS.event_log],
      "GET /v1/workspace/event-logs/elog_1/analysis": {
        ...TIMED_ANALYSIS,
        summary: { ...TIMED_ANALYSIS.summary, firstEnableObserved: false, enablementObserved: false },
      },
    });
    const onDecorations = vi.fn();
    const user = userEvent.setup();
    renderPanel({ ...SECTION, runs: [RUN], activeRunId: 7 } as unknown as SimulationSectionValue, onDecorations);

    await user.click(await screen.findByRole("button", { name: /^erp\.csv/ }));
    await user.click(await screen.findByRole("button", { name: /Reale contro simulato$/ }));

    expect(await screen.findByText("Confronto con il log reale")).toBeInTheDocument();

    expect(screen.getByText("Questa simulazione è vicina al log reale")).toBeInTheDocument();
    const process = screen.getAllByRole("table").find((table) => within(table).queryByRole("row", { name: /Costo per caso/ }))!;
    expect(within(within(process).getByRole("row", { name: /Durata media di un caso/ })).getByText("+5%")).toBeInTheDocument();
    expect(within(process).getByRole("row", { name: /Costo per caso/ })).toHaveTextContent("il log non ha costi");
    expect(screen.getByText(/Nella simulazione un caso dura in tutto/)).toBeInTheDocument();

    const activities = screen.getByRole("table", { name: /Tempo di lavoro e attesa medi per attività/ });
    expect(within(activities).getByRole("row", { name: /Ricevi richiesta/ })).toHaveTextContent("+50%");
    expect(within(activities).getByRole("row", { name: /Ricevi richiesta/ })).toHaveTextContent("il log non registra l'attesa prima di questa attività");
    expect(screen.getByText(/1 attività del log non è nel modello/).closest("section")).toHaveTextContent("Approva");
    expect(screen.getByText("1 attività simulata non compare mai nel log")).toBeInTheDocument();

    expect(onDecorations).toHaveBeenLastCalledWith(null);
    await user.click(screen.getByRole("button", { name: "Mostra sul processo" }));
    expect(onDecorations).toHaveBeenLastCalledWith({
      items: [{ elementId: "T1", markers: ["sim-fidelity-far"], badge: "+50%", badgeTone: "danger" }],
      legend: { label: "simulation.eventLog.compare.legend", levels: "simulation.eventLog.compare.fidelity" },
    });
  });

  it("requests one aggregate report for the selected replication group", async () => {
    routes({
      "GET /v1/workspace/processes/acquisti/event-logs": [ANALYSIS.event_log],
      "GET /v1/workspace/event-logs/elog_1/analysis": TIMED_ANALYSIS,
    });
    const first = { ...RUN, request: { replication_group: "batch-a", replication_index: 1 } };
    const second = { ...RUN, id: 8, request: { replication_group: "batch-a", replication_index: 2 } };
    const user = userEvent.setup();
    renderPanel({ ...SECTION, runs: [first, second], activeRunId: 8 } as unknown as SimulationSectionValue);

    await user.click(await screen.findByRole("button", { name: /^erp\.csv/ }));
    await user.click(await screen.findByRole("button", { name: /Reale contro simulato$/ }));
    await waitFor(() => expect(calls("GET", "/v1/workspace/event-logs/elog_1/validation")).toHaveLength(2));
    expect(http.mock.calls.some(([path]) => path.includes("run_ids=7&run_ids=8"))).toBe(true);
  });

  it("flags legacy runs without a fixed start and hides their misleading aggregate KPIs", async () => {
    routes({
      "GET /v1/workspace/processes/acquisti/event-logs": [ANALYSIS.event_log],
      "GET /v1/workspace/event-logs/elog_1/analysis": TIMED_ANALYSIS,
      "GET /v1/workspace/event-logs/elog_1/validation": {
        referenceCases: 1000, replications: 2, simulatedCases: [1000, 1000],
        firstWaitSimulated: null, quality: { rowsExcluded: 0, eventsWithoutStart: 0 },
        provenance: { eventLogId: "elog_1", runs: [{ runId: 7, seed: 1, engine: "Prosimos", engineVersion: "1", startDate: null, warmupCases: 0 }] },
      },
    });
    const user = userEvent.setup();
    renderPanel({ ...SECTION, runs: [{ ...RUN, request: { start_date: null } }], activeRunId: 7 } as unknown as SimulationSectionValue);

    await user.click(await screen.findByRole("button", { name: /^erp\.csv/ }));
    await user.click(await screen.findByRole("button", { name: /Reale contro simulato$/ }));
    expect((await screen.findAllByText("Simulazioni senza data di inizio")).length).toBeGreaterThan(0);
    expect(screen.queryByRole("row", { name: /Durata media di un caso/ })).not.toBeInTheDocument();
  });

  it("asks for a run when there is nothing to compare yet", async () => {
    routes({
      "GET /v1/workspace/processes/acquisti/event-logs": [ANALYSIS.event_log],
      "GET /v1/workspace/event-logs/elog_1/analysis": TIMED_ANALYSIS,
    });
    const openPanel = vi.fn();
    const user = userEvent.setup();
    renderPanel({ ...SECTION, openPanel } as unknown as SimulationSectionValue);

    await user.click(await screen.findByRole("button", { name: /^erp\.csv/ }));
    await user.click(await screen.findByRole("button", { name: /Reale contro simulato$/ }));
    expect(await screen.findByText("Nessun run completato da confrontare")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Scenario" }));
    expect(openPanel).toHaveBeenCalledWith("scenario");
  });

  it("asks before deleting a log and deletes it only on confirm", async () => {
    routes({ "DELETE /v1/workspace/event-logs/elog_1": undefined });
    const user = userEvent.setup();
    renderPanel();

    await user.click(await screen.findByRole("button", { name: "Elimina erp.csv" }));
    const dialog = await screen.findByRole("dialog", { name: "Eliminare erp.csv?" });
    expect(calls("DELETE", "/v1/workspace/event-logs/elog_1")).toHaveLength(0);

    await user.click(within(dialog).getByRole("button", { name: "Elimina il log" }));
    await waitFor(() => expect(calls("DELETE", "/v1/workspace/event-logs/elog_1")).toHaveLength(1));
  });

  it("says when the report of a mapped log cannot be read and offers to remap", async () => {
    routes({ "GET /v1/workspace/processes/acquisti/event-logs": [ANALYSIS.event_log] });
    const listAndPreview = http.getMockImplementation()!;
    http.mockImplementation(async (path: string, options?: { method?: string }) => {
      if (path === "/v1/workspace/event-logs/elog_1/analysis") throw new HttpError(500, "500 Internal Server Error");
      return listAndPreview(path, options);
    });
    const user = userEvent.setup();
    renderPanel();

    await user.click(await screen.findByRole("button", { name: /^erp\.csv/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Non riesco a leggere il report");
    await user.click(screen.getByRole("button", { name: "Rivedi le colonne" }));
    expect(await screen.findByRole("region", { name: "Righe dell'event log" })).toBeInTheDocument();
  });
});
