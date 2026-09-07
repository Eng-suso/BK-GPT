import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import "@/lib/i18n";
import type { ProjectProcess } from "../types";

const http = vi.fn();

vi.mock("@/lib/http", async () => {
  const actual = await vi.importActual<typeof import("@/lib/http")>("@/lib/http");
  return { ...actual, http: (path: string, options?: unknown) => http(path, options) };
});

const { ProcessFormDialog } = await import("./ProcessFormDialog");

const PROCESS: ProjectProcess = {
  id: "evasione-ordini",
  projectId: "ciclo-ordini",
  bpmnModelId: "evasione-ordini-bpmn",
  name: "Evasione ordini",
  stage: "AS-IS",
  status: "In corso",
  owner: "Logistica",
  readiness: 40,
};

const API_PROCESS = {
  id: PROCESS.id,
  project_id: PROCESS.projectId,
  bpmn_model_id: PROCESS.bpmnModelId,
  name: PROCESS.name,
  stage: PROCESS.stage,
  status: PROCESS.status,
  owner: PROCESS.owner,
  readiness: PROCESS.readiness,
};

function renderDialog(process: ProjectProcess | null) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const onOpenChange = vi.fn();
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  render(
    <ProcessFormDialog
      open
      onOpenChange={onOpenChange}
      projectId={PROCESS.projectId}
      process={process}
    />,
    { wrapper },
  );
  return { onOpenChange };
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("ProcessFormDialog", () => {
  it("registers a process on the project the consultant is looking at", async () => {
    const user = userEvent.setup();
    http.mockResolvedValue(API_PROCESS);
    const { onOpenChange } = renderDialog(null);

    await user.type(
      screen.getByRole("textbox", { name: /nome processo/i }),
      "Evasione ordini",
    );
    await user.click(screen.getByRole("button", { name: /crea processo/i }));

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(http).toHaveBeenCalledWith(
      `/v1/workspace/projects/${PROCESS.projectId}/processes`,
      expect.objectContaining({
        method: "POST",
        body: expect.objectContaining({
          name: "Evasione ordini",
          stage: "AS-IS",
          status: "Bozza",
        }),
      }),
    );
  });

  it("edits the record in place, prefilled from the process", async () => {
    const user = userEvent.setup();
    http.mockResolvedValue({ ...API_PROCESS, owner: "Customer service" });
    const { onOpenChange } = renderDialog(PROCESS);

    const owner = screen.getByRole("textbox", { name: /owner/i });
    expect(owner).toHaveValue("Logistica");
    await user.clear(owner);
    await user.type(owner, "Customer service");
    await user.click(screen.getByRole("button", { name: /salva modifiche/i }));

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(http).toHaveBeenCalledWith(
      `/v1/workspace/processes/${PROCESS.id}`,
      expect.objectContaining({
        method: "PATCH",
        body: expect.objectContaining({ owner: "Customer service", readiness: 40 }),
      }),
    );
  });

  it("refuses a process with no name and writes nothing", async () => {
    const user = userEvent.setup();
    http.mockResolvedValue(API_PROCESS);
    renderDialog(null);

    await user.click(screen.getByRole("button", { name: /crea processo/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /nome processo è obbligatorio/i,
    );
    expect(http).not.toHaveBeenCalled();
  });
});
