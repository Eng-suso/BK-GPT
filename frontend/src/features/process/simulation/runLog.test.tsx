import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import "@/lib/i18n";

import { RunLogDownload } from "./RunLogDownload";
import { runLogFilename } from "./runLog";
import type { SimulationRun } from "./simulationTypes";

const RUN = { id: 42, request: { workspace_scenario: { id: 3, revision: 5, baseline_revision: 2 } } } as unknown as SimulationRun;

afterEach(() => vi.unstubAllGlobals());

describe("log simulato da scaricare (SIM-06b)", () => {
  it("mette scenario e revisione nel nome del file, come il backend", () => {
    expect(runLogFilename(RUN, "csv")).toBe("simulation-run-42-scenario-3-rev-5.csv");
    expect(runLogFilename({ id: 7, request: {} }, "xes")).toBe("simulation-run-7.xes");
  });

  it("dice quando il log di un run vecchio non c'è", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "Nessun log" }), { status: 404 })));
    render(<RunLogDownload run={RUN} />);

    await userEvent.setup().click(screen.getByRole("button", { name: "Scarica il log simulato in CSV" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("i run più vecchi non lo conservano");
    expect(screen.getByRole("button", { name: "Scarica il log simulato in XES" })).toBeEnabled();
  });
});
