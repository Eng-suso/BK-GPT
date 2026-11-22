import React from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import "@/lib/i18n";
import { TaskDurationFields } from "./TaskDurationFields";
import type { DurationDraft } from "./simulationScenario";

function Harness({ initial, kind = "duration" }: { initial: DurationDraft; kind?: "arrival" | "duration" }) {
  const [task, setTask] = React.useState(initial);
  return <>
    <TaskDurationFields elementId="Task_1" taskName="Valuta richiesta" task={task} kind={kind} onChange={setTask} />
    <output data-testid="duration">{JSON.stringify(task)}</output>
  </>;
}

describe("simulation duration disclosure", () => {
  it("explains arrivals and keeps every imported distribution parameter editable", async () => {
    const user = userEvent.setup();
    render(<Harness kind="arrival" initial={{ meanMinutes: 960, distribution: "norm", stdMinutes: 20, minMinutes: 10, maxMinutes: 1900 }} />);
    expect(screen.getByText("Tempo tra l'arrivo di due richieste")).toBeInTheDocument();
    expect(screen.getByText(/media di 960 minuti/)).toBeInTheDocument();
    const details = screen.getByText("Dettagli tecnici e limiti").closest("details")!;
    expect(details).not.toHaveAttribute("open");
    await user.click(within(details).getByText("Dettagli tecnici e limiti"));
    expect(details).toHaveAttribute("open");
    expect(within(details).getByLabelText("Dev. std, min · Valuta richiesta")).toHaveValue(20);
    expect(within(details).getByLabelText("Minimo, min · Valuta richiesta")).toHaveValue(10);
    expect(within(details).getByLabelText("Massimo, min · Valuta richiesta")).toHaveValue(1900);
    expect(within(details).getByText("Task_1")).toBeInTheDocument();
    expect(JSON.parse(screen.getByTestId("duration").textContent ?? "{}")).toMatchObject({ stdMinutes: 20, minMinutes: 10, maxMinutes: 1900 });
  });

  it("shows required uniform bounds immediately", () => {
    render(<Harness initial={{ meanMinutes: 20, distribution: "uniform", minMinutes: 5, maxMinutes: 30 }} />);
    expect(screen.getByLabelText("Minimo, min · Valuta richiesta")).toBeVisible();
    expect(screen.getByLabelText("Massimo, min · Valuta richiesta")).toBeVisible();
    expect(screen.getByText(/fra 5 e 30 minuti/)).toBeInTheDocument();
  });
});
