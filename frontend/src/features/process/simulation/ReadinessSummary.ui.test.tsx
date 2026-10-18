import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import "@/lib/i18n";

import { ReadinessSummary } from "./ReadinessSummary";
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
