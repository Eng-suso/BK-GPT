import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import "@/lib/i18n";

import { TaskInstances } from "./TaskInstances";
import { instancesIssue } from "./instances";
import { DEFAULT_SCENARIO, scenarioParameterIssues, scenarioToInput, type TaskDraft } from "./simulationScenario";

const cfg: TaskDraft = { meanMinutes: 10, distribution: "norm", resourceId: "r1" };

describe("istanze per caso (SIM-11h)", () => {
  it("un numero fisso del BPMN si legge e non si cambia", () => {
    render(<TaskInstances task={{ element_id: "T", name: "Firma", type: "task", multi_instance: "sequential", instances: 3 }}
      cfg={cfg} onChange={() => undefined} />);
    expect(screen.getByText("Multi-istanza dal BPMN: 3 istanze per caso, una dopo l'altra.")).toBeInTheDocument();
    expect(screen.queryByRole("spinbutton")).not.toBeInTheDocument();
  });

  it("su una collezione le imposta il consulente", () => {
    const onChange = vi.fn();
    render(<TaskInstances task={{ element_id: "T", name: "Firma", type: "task", multi_instance: "parallel", instances: null }}
      cfg={cfg} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText("Istanze per caso · Firma"), { target: { value: "4" } });
    expect(onChange).toHaveBeenCalledWith({ ...cfg, instances: 4 });
    expect(screen.getByText(/in parallelo/)).toBeInTheDocument();
  });

  it("un valore fuori scala si segnala e blocca il run", () => {
    render(<TaskInstances task={{ element_id: "T", name: "Firma", type: "task", multi_instance: "parallel" }}
      cfg={{ ...cfg, instances: 80 }} onChange={() => undefined} />);
    expect(screen.getByRole("alert")).toHaveTextContent("da 1 a 50");
    expect(screen.getByLabelText("Istanze per caso · Firma")).toHaveAttribute("aria-invalid", "true");
    expect(instancesIssue(2.5)).toBe("range");
    expect(instancesIssue(undefined)).toBeNull();
    const draft = { ...structuredClone(DEFAULT_SCENARIO), tasks: { T: { ...cfg, instances: 80 } } };
    expect(scenarioParameterIssues(draft).durations).toBe(1);
  });

  it("un'attività senza multi-istanza non mostra nulla, e la richiesta porta le istanze solo sopra una", () => {
    const { container } = render(<TaskInstances task={{ element_id: "T", name: "Firma", type: "task" }} cfg={cfg} onChange={() => undefined} />);
    expect(container).toBeEmptyDOMElement();
    const input = scenarioToInput({ ...structuredClone(DEFAULT_SCENARIO), tasks: { A: { ...cfg, instances: 4 }, B: { ...cfg, instances: 1 } } }, null);
    expect(input.tasks?.map((t) => t.instances)).toEqual([4, undefined]);
  });
});
