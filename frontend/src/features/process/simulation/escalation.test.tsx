import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { i18n } from "@/lib/i18n";

import { SimulationConfigRail } from "./SimulationConfigRail";
import { formatAfter } from "./escalation";
import { DEFAULT_SCENARIO, type ScenarioDraft } from "./simulationScenario";
import type { ScenarioTemplate } from "./simulationTypes";


describe("escalation a tempo (SIM-35)", () => {
  it("dice dopo quanto scatta il timer in parole", () => {
    const t = i18n.getFixedT("it", "process");
    expect(formatAfter(172_800, t)).toBe("48 ore");
    expect(formatAfter(1800, t)).toBe("30 minuti");
    expect(formatAfter(5400, t)).toBe("1 ora e 30 minuti");
    expect(formatAfter(4 * 86_400 + 3600, t)).toBe("4 giorni e 1 ora");
  });

  it("nel pannello la decisione del timer non chiede percentuali né regole", () => {
    const template = {
      resources: [],
      standard_calendar: null,
      tasks: [{ element_id: "T1", name: "Approva", type: "task" }],
      gateways: [
        { element_id: "B_late", name: "Oltre 48 ore", type: "exclusiveGateway",
          branches: [{ flow_id: "F_ok", flow_name: "", target_name: "Paga" }, { flow_id: "F_late", flow_name: "", target_name: "Sollecita" }],
          escalation: { activity_id: "T1", after_seconds: 172_800, normal_flow_id: "F_ok" } },
      ],
    } as unknown as ScenarioTemplate;
    const draft: ScenarioDraft = {
      ...structuredClone(DEFAULT_SCENARIO),
      tasks: { T1: { meanMinutes: 20, distribution: "norm", resourceId: "" } },
      gateways: { B_late: { F_ok: 50, F_late: 50 } },
    };
    render(<SimulationConfigRail template={template} templateLoading={false} draft={draft} onDraftChange={() => undefined}
      isRunning={false} error={null} onRun={() => undefined} focusElementId={null} />);

    const note = document.querySelector('[data-escalation="B_late"]');
    expect(note).toHaveTextContent("Escalation a tempo dopo 48 ore su «Approva».");
    expect(screen.queryByLabelText("Sollecita")).not.toBeInTheDocument();
  });
});
