import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import "@/lib/i18n";

vi.mock("@/features/projects/api", () => ({
  useProjectsQuery: () => ({
    isLoading: false,
    isError: false,
    data: [
      {
        id: "p-acquisti",
        name: "Riorganizzazione acquisti",
        client: "Esaote",
        processItems: [{ id: "proc-p2p", name: "Procure to pay" }],
      },
      { id: "p-hr", name: "Processi HR", client: "Barilla", processItems: [] },
    ],
  }),
}));

const { UploadDestinationDialog } = await import("./UploadDestinationDialog");

describe("UploadDestinationDialog", () => {
  it("un file messo in un processo porta progetto e processo", async () => {
    const onConfirm = vi.fn();
    render(<UploadDestinationDialog open initial={null} onConfirm={onConfirm} onClose={vi.fn()} />);

    const choose = screen.getByRole("button", { name: "Scegli il file" });
    expect(choose).toBeDisabled();

    await userEvent.selectOptions(screen.getByLabelText("Progetto"), "p-acquisti");
    await userEvent.selectOptions(screen.getByLabelText(/Processo/), "proc-p2p");
    expect(screen.getByText(/evidenza di questo processo/)).toBeInTheDocument();
    await userEvent.click(choose);

    expect(onConfirm).toHaveBeenCalledWith({
      projectId: "p-acquisti",
      processId: "proc-p2p",
      label: "Riorganizzazione acquisti · Procure to pay",
    });
  });

  it("cambiando progetto il processo scelto si azzera", async () => {
    const onConfirm = vi.fn();
    render(
      <UploadDestinationDialog
        open
        initial={{ projectId: "p-acquisti", processId: "proc-p2p" }}
        onConfirm={onConfirm}
        onClose={vi.fn()}
      />,
    );

    await userEvent.selectOptions(screen.getByLabelText("Progetto"), "p-hr");
    await userEvent.click(screen.getByRole("button", { name: "Scegli il file" }));

    expect(onConfirm).toHaveBeenCalledWith({ projectId: "p-hr", processId: null, label: "Processi HR" });
  });
});
