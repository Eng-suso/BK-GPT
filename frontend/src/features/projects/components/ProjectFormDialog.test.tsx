import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import "@/lib/i18n";
import type { Project } from "../types";

const http = vi.fn();

vi.mock("@/lib/http", async () => {
  const actual = await vi.importActual<typeof import("@/lib/http")>("@/lib/http");
  return { ...actual, http: (path: string, options?: unknown) => http(path, options) };
});

const { ProjectFormDialog } = await import("./ProjectFormDialog");

const PROJECT: Project = {
  id: "ciclo-ordini",
  clientId: "esaote",
  client: "Esaote",
  name: "Ciclo ordini",
  objective: "Ricostruire l'AS-IS del ciclo ordini e misurare il lead time.",
  phase: "AS-IS",
  status: "In corso",
  progress: 40,
  processes: 1,
  nextStep: "Interviste reparto ordini",
  milestones: ["Kickoff"],
  openIssues: [],
  deliverables: ["Report AS-IS"],
  processItems: [],
};

const API_PROJECT = {
  id: PROJECT.id,
  client_id: PROJECT.clientId,
  client: "Esaote",
  name: PROJECT.name,
  objective: PROJECT.objective,
  phase: PROJECT.phase,
  status: PROJECT.status,
  progress: PROJECT.progress,
  processes: PROJECT.processes,
  next_step: PROJECT.nextStep,
  milestones: PROJECT.milestones,
  open_issues: PROJECT.openIssues,
  deliverables: PROJECT.deliverables,
  process_items: [],
};

function renderDialog(project: Project | null) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const onOpenChange = vi.fn();
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  render(
    <ProjectFormDialog open onOpenChange={onOpenChange} project={project} />,
    { wrapper },
  );
  return { onOpenChange };
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("ProjectFormDialog", () => {
  it("puts the engagement objective in the form, prefilled from the record", () => {
    http.mockResolvedValue([]);
    renderDialog(PROJECT);

    expect(
      screen.getByRole("textbox", { name: /obiettivo dell'incarico/i }),
    ).toHaveValue(PROJECT.objective);
  });

  it("saves the objective onto the project record", async () => {
    const user = userEvent.setup();
    http.mockImplementation((path: string) =>
      path === "/v1/workspace/clients"
        ? Promise.resolve([])
        : Promise.resolve(API_PROJECT),
    );
    const { onOpenChange } = renderDialog(PROJECT);

    const objective = screen.getByRole("textbox", {
      name: /obiettivo dell'incarico/i,
    });
    await user.clear(objective);
    await user.type(objective, "Validare l'AS-IS con gli stakeholder.");
    await user.click(screen.getByRole("button", { name: /salva modifiche/i }));

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(http).toHaveBeenCalledWith(
      `/v1/workspace/projects/${PROJECT.id}`,
      expect.objectContaining({
        method: "PATCH",
        body: expect.objectContaining({
          objective: "Validare l'AS-IS con gli stakeholder.",
          phase: "AS-IS",
          status: "In corso",
        }),
      }),
    );
  });

  it("refuses to create a project with no client and writes nothing", async () => {
    const user = userEvent.setup();
    http.mockResolvedValue([]);
    renderDialog(null);

    await user.type(
      screen.getByRole("textbox", { name: /nome progetto/i }),
      "Ciclo ordini",
    );
    await user.click(screen.getByRole("button", { name: /crea progetto/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /seleziona il cliente/i,
    );
    expect(http).not.toHaveBeenCalledWith(
      "/v1/workspace/projects",
      expect.anything(),
    );
  });
});
