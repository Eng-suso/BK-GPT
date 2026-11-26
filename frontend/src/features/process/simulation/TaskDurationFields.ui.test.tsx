import React from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import "@/lib/i18n";
import { TaskDurationFields } from "./TaskDurationFields";
import { arrivalsRunFaster, type DurationDraft } from "./simulationScenario";

function Harness({ initial, kind = "duration" }: { initial: DurationDraft; kind?: "arrival" | "duration" }) {
  const [task, setTask] = React.useState(initial);
  const faster = kind === "arrival" ? arrivalsRunFaster(task) : null;
  return <>
    <TaskDurationFields elementId="Task_1" taskName="Valuta richiesta" task={task} kind={kind} faster={faster} onChange={setTask} />
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

  it("warns when arrivals will come denser than written and offers the fix (IMP-01)", async () => {
    const user = userEvent.setup();
    render(<Harness kind="arrival" initial={{ meanMinutes: 1805 / 60, distribution: "expon", minMinutes: 5 / 60, maxMinutes: 60 }} />);
    const notice = screen.getByText("I casi arriveranno più spesso del previsto").closest("section")!;
    expect(notice).toHaveTextContent("I casi arriveranno più spesso del previsto");
    expect(notice).toHaveTextContent("in media arriva un caso ogni 21 min invece che ogni 30 min, circa il 45% di casi in più");
    expect(notice).not.toHaveTextContent(/esponenzial|expon|troncat/i);
    await user.click(within(notice).getByRole("button", { name: "Porta il massimo a 2h 30 min" }));
    expect(screen.queryByText("I casi arriveranno più spesso del previsto")).not.toBeInTheDocument();
    expect(JSON.parse(screen.getByTestId("duration").textContent ?? "{}").maxMinutes).toBeCloseTo(150.4, 1);
  });

  it("rounds the mean in the sentence without hiding short steps", () => {
    render(<Harness initial={{ meanMinutes: 2 / 60, distribution: "fixed" }} />);
    expect(screen.getByText("Ogni esecuzione dura 0.0333 minuti.")).toBeInTheDocument();
  });

  it("does not warn for task durations with the same numbers", () => {
    render(<Harness initial={{ meanMinutes: 1805 / 60, distribution: "expon", minMinutes: 5 / 60, maxMinutes: 60 }} />);
    expect(screen.queryByText("I casi arriveranno più spesso del previsto")).not.toBeInTheDocument();
  });

  it("shows required uniform bounds immediately", () => {
    render(<Harness initial={{ meanMinutes: 20, distribution: "uniform", minMinutes: 5, maxMinutes: 30 }} />);
    expect(screen.getByLabelText("Minimo, min · Valuta richiesta")).toBeVisible();
    expect(screen.getByLabelText("Massimo, min · Valuta richiesta")).toBeVisible();
    expect(screen.getByText(/fra 5 e 30 minuti/)).toBeInTheDocument();
  });
});
