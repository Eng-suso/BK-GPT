import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import "@/lib/i18n";
import type { Milestone } from "@/contracts/workspace";

const http = vi.fn();

vi.mock("@/lib/http", async () => {
  const actual = await vi.importActual<typeof import("@/lib/http")>("@/lib/http");
  return { ...actual, http: (path: string, options?: unknown) => http(path, options) };
});

const { MilestoneTracker } = await import("./MilestoneTracker");

const MILESTONES: Milestone[] = [
  { title: "Kickoff", status: "done", completedAt: "2026-03-04T09:00:00Z" },
  { title: "Validazione AS-IS", status: "planned", completedAt: null },
];

function renderTracker(milestones: Milestone[] = MILESTONES) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  render(
    <MilestoneTracker projectId="ciclo-ordini" milestones={milestones} />,
    { wrapper },
  );
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("MilestoneTracker", () => {
  it("reads each milestone's state off the record, not off its position", () => {
    renderTracker([
      { title: "Kickoff", status: "planned", completedAt: null },
      { title: "Validazione AS-IS", status: "done", completedAt: "2026-03-04T09:00:00Z" },
    ]);

    expect(screen.getByRole("checkbox", { name: /Kickoff/ })).not.toBeChecked();
    expect(
      screen.getByRole("checkbox", { name: /Validazione AS-IS/ }),
    ).toBeChecked();
  });

  it("writes the milestone the consultant marks as reached", async () => {
    const user = userEvent.setup();
    http.mockResolvedValue({
      id: "ciclo-ordini",
      client_id: "esaote",
      client: "Esaote",
      name: "Ciclo ordini",
      objective: "",
      phase: "AS-IS",
      status: "In corso",
      progress: 40,
      processes: 0,
      next_step: "Interviste",
      milestones: [],
      open_issues: [],
      deliverables: [],
      process_items: [],
    });
    renderTracker();

    await user.click(
      screen.getByRole("checkbox", { name: /Validazione AS-IS/ }),
    );

    await waitFor(() => expect(http).toHaveBeenCalled());
    expect(http).toHaveBeenCalledWith(
      "/v1/workspace/projects/ciclo-ordini",
      expect.objectContaining({
        method: "PATCH",
        body: {
          milestones: [
            {
              title: "Kickoff",
              status: "done",
              completed_at: "2026-03-04T09:00:00Z",
            },
            { title: "Validazione AS-IS", status: "done", completed_at: null },
          ],
        },
      }),
    );
  });

  it("says the record has no milestones instead of showing an empty tick list", () => {
    renderTracker([]);

    expect(screen.getByText(/nessuna milestone registrata/i)).toBeVisible();
    expect(screen.queryByRole("checkbox")).toBeNull();
  });
});
