import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nextProvider } from "react-i18next";
import { render, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { setupUser } from "@/test/user";

import { i18n } from "@/lib/i18n";

// Il confine e' la risposta HTTP: il test passa anche dal contratto e dalla
// mappatura, non solo dal componente.
const http = vi.fn<(path: string, init?: { body?: unknown }) => Promise<unknown>>();

vi.mock("@/lib/http", () => ({ http: (path: string, init?: { body?: unknown }) => http(path, init) }));

const { NotificationsMenu } = await import("./NotificationsMenu");
const { notificationHref } = await import("./api");

type ApiNotification = {
  id: string;
  kind: string;
  occurred_at: string;
  read: boolean;
  process_id: string;
  process_name: string;
  project_id: string;
  project_name: string;
  client_name: string;
  bpmn_model_id: string | null;
  count: number;
  version: number | null;
  detail: string;
  run_id: number | null;
};

function notification(overrides: Partial<ApiNotification> = {}): ApiNotification {
  return {
    id: "conformance:bpmn-1:2026-09-20T09:00:00+00:00",
    kind: "conformance_findings",
    occurred_at: "2026-09-20T09:00:00+00:00",
    read: false,
    process_id: "proc-1",
    process_name: "Ciclo passivo",
    project_id: "proj-1",
    project_name: "Riorganizzazione acquisti",
    client_name: "Esaote",
    bpmn_model_id: "bpmn-1",
    count: 2,
    version: null,
    detail: "not_conformant",
    run_id: null,
    ...overrides,
  };
}

function backendReturns(items: ApiNotification[]) {
  http.mockImplementation(async (path) => ({
    items: path.includes("/read") ? items.map((item) => ({ ...item, read: true })) : items,
    unread: path.includes("/read") ? 0 : items.filter((item) => !item.read).length,
  }));
}

function renderMenu() {
  const onNavigate = vi.fn();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    </I18nextProvider>
  );
  render(<NotificationsMenu onNavigate={onNavigate} />, { wrapper });
  return { onNavigate };
}

beforeAll(async () => {
  await i18n.changeLanguage("it");
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("NotificationsMenu", () => {
  it("counts what is unread instead of a fixed badge", async () => {
    backendReturns([notification(), notification({ id: "b", read: true })]);
    renderMenu();

    expect(
      await screen.findByRole("button", { name: /1 non lett/i }, { timeout: 5000 }),
    ).toBeInTheDocument();
  });

  it("shows no badge when there is nothing to read", async () => {
    backendReturns([notification({ read: true })]);
    renderMenu();

    const bell = await screen.findByRole("button", { name: "Avvisi" }, { timeout: 5000 });
    expect(bell).toHaveTextContent("");
  });

  it("says what happened, and where", async () => {
    const user = setupUser();
    backendReturns([notification()]);
    renderMenu();

    await user.click(await screen.findByRole("button", { name: /Avvisi/ }, { timeout: 5000 }));

    expect(await screen.findByText(/2 punti da rivedere/)).toBeInTheDocument();
    // Senza il percorso, "Ciclo passivo" non dice di quale cliente si parla.
    expect(screen.getByText(/Esaote · Riorganizzazione acquisti · Ciclo passivo/)).toBeInTheDocument();
  });

  it("opens the notification where the thing can be looked at, and marks it read", async () => {
    const user = setupUser();
    backendReturns([notification()]);
    const { onNavigate } = renderMenu();
    await user.click(await screen.findByRole("button", { name: /Avvisi/ }, { timeout: 5000 }));

    await user.click(await screen.findByText(/2 punti da rivedere/));

    expect(onNavigate).toHaveBeenCalledWith("/projects/proj-1/processes/proc-1?view=canvas");
    expect(http).toHaveBeenCalledWith(
      "/v1/workspace/notifications/read",
      expect.objectContaining({ body: { ids: ["conformance:bpmn-1:2026-09-20T09:00:00+00:00"] } }),
    );
  });

  it("separates 'nothing happened' from 'the list could not be loaded'", async () => {
    const user = setupUser();
    http.mockRejectedValue(new Error("backend giu'"));
    renderMenu();

    await user.click(await screen.findByRole("button", { name: /Avvisi/ }, { timeout: 5000 }));

    // Un guasto mostrato come "nessun avviso" fa concludere che va tutto bene.
    expect(await screen.findByText(/Impossibile caricare gli avvisi/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Riprova/ })).toBeInTheDocument();
  });

  it("says the workspace is quiet when there is nothing", async () => {
    const user = setupUser();
    backendReturns([]);
    renderMenu();

    await user.click(await screen.findByRole("button", { name: /Avvisi/ }, { timeout: 5000 }));

    expect(await screen.findByText("Nessun avviso")).toBeInTheDocument();
  });
});

describe("notificationHref", () => {
  const base = {
    id: "x",
    occurredAt: "2026-09-20T09:00:00+00:00",
    read: false,
    processId: "proc-1",
    processName: "Ciclo passivo",
    projectId: "proj-1",
    projectName: "P",
    clientName: "C",
    count: 0,
    version: null,
    detail: "",
    runId: null,
  };

  it("sends each kind where that thing is looked at", () => {
    expect(notificationHref({ ...base, kind: "conformance_findings" })).toBe(
      "/projects/proj-1/processes/proc-1?view=canvas",
    );
    expect(notificationHref({ ...base, kind: "simulation_done" })).toContain("/simulation/");
    // Un piano pronto o fallito si guarda (e si rilancia) nel processo.
    expect(notificationHref({ ...base, kind: "plan_failed" })).toBe(
      "/projects/proj-1/processes/proc-1",
    );
  });
});
