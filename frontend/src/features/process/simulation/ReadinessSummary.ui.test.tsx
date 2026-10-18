import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import "@/lib/i18n";

import { ReadinessSummary } from "./ReadinessSummary";
import { uncertainFactors } from "./sensitivity";
import { buildInputConfidence } from "./simulationProvenance";
import { DEFAULT_SCENARIO, seedDraftFromTemplate } from "./simulationScenario";
import type { ScenarioTemplate } from "./simulationTypes";

const TEMPLATE: ScenarioTemplate = { tasks: [{ element_id: "T", name: "Verifica", type: "task" }], gateways: [] };

describe("readiness summary (SIM-18)", () => {
  it("shows the calendars row and explains the formula on request", async () => {
    const user = userEvent.setup();
    const draft = seedDraftFromTemplate(structuredClone(DEFAULT_SCENARIO), TEMPLATE);
    render(<ReadinessSummary confidence={buildInputConfidence(draft, TEMPLATE, null)} provenance={null} />);

    expect(screen.getByText("Calendari")).toBeInTheDocument();
    const formula = screen.getByText("Come si calcola");
    expect(screen.getByText(/Una riga è alta da 75%/)).not.toBeVisible();
    await user.click(formula);
    expect(screen.getByText(/Una riga è alta da 75%/)).toBeVisible();
    expect(screen.getByText(/Non entrano ancora: costi, attributi del caso, code e ritardi/)).toBeVisible();
  });

  it("keeps the compact form without the formula", () => {
    const draft = seedDraftFromTemplate(structuredClone(DEFAULT_SCENARIO), TEMPLATE);
    render(<ReadinessSummary dense confidence={buildInputConfidence(draft, TEMPLATE, null)} provenance={null} />);
    expect(screen.queryByText("Come si calcola")).not.toBeInTheDocument();
  });
});

describe("sensitivity launch (SIM-25)", () => {
  it("counts the uncertain assumptions and the runs, then starts the study", async () => {
    const user = userEvent.setup();
    const draft = seedDraftFromTemplate(structuredClone(DEFAULT_SCENARIO), TEMPLATE);
    const confidence = buildInputConfidence(draft, TEMPLATE, null);
    const factors = uncertainFactors(confidence, TEMPLATE, draft, "Tempo fra due arrivi");
    let started = 0;
    render(<ReadinessSummary confidence={confidence} provenance={null} sensitivity={{ factors, onStart: () => { started += 1; } }} />);

    expect(factors.map((f) => f.kind)).toEqual(["duration", "arrival"]);
    expect(screen.getByText(/2 ipotesi incerte, variate di ±20% una alla volta: 5 simulazioni/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Analizza la sensitività" }));
    expect(started).toBe(1);
  });

  it("says when there is nothing to vary", () => {
    const draft = seedDraftFromTemplate(structuredClone(DEFAULT_SCENARIO), TEMPLATE);
    render(<ReadinessSummary confidence={buildInputConfidence(draft, TEMPLATE, null)} provenance={null} sensitivity={{ factors: [], onStart: () => {} }} />);
    expect(screen.getByText(/Nessuna ipotesi a confidenza bassa o media/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Analizza la sensitività" })).not.toBeInTheDocument();
  });
});

describe("source conflicts (SIM-17)", () => {
  it("asks which source holds, naming both durations", () => {
    const draft = seedDraftFromTemplate(structuredClone(DEFAULT_SCENARIO), TEMPLATE);
    const conflicts = [{
      elementId: "T", name: "Verifica", spread: 1,
      shortest: { kind: "claim" as const, label: "Procedure.pdf", seconds: 600 },
      longest: { kind: "log" as const, label: "Log 2025", seconds: 1200 },
      sources: [],
    }];
    render(<ReadinessSummary confidence={buildInputConfidence(draft, TEMPLATE, null)} provenance={null} conflicts={conflicts} />);
    expect(screen.getByText("Fonti in disaccordo")).toBeInTheDocument();
    expect(screen.getByText("«Verifica»: «Procedure.pdf» dice 10 min, «Log 2025» dice 20 min. Quale vale, e per quali casi?")).toBeInTheDocument();
  });

  it("stays silent without conflicts", () => {
    const draft = seedDraftFromTemplate(structuredClone(DEFAULT_SCENARIO), TEMPLATE);
    render(<ReadinessSummary confidence={buildInputConfidence(draft, TEMPLATE, null)} provenance={null} />);
    expect(screen.queryByText("Fonti in disaccordo")).not.toBeInTheDocument();
  });
});
