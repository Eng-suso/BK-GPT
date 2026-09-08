import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import { EmptyState } from "./EmptyState";
import type { ChatScope } from "../chatScope";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { returnObjects?: boolean }) =>
      options?.returnObjects ? [key] : key,
  }),
}));

const EMPTY_CANVAS = `<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">
  <bpmn:process id="Process_Workspace" name="Idem" isExecutable="false" />
</bpmn:definitions>`;

const MODELLED_CANVAS = `<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">
  <bpmn:process id="Process_Workspace" name="Idem" isExecutable="false">
    <bpmn:userTask id="Task_1" name="Registra la richiesta" />
  </bpmn:process>
</bpmn:definitions>`;

function canvasScope(xml: string | null): ChatScope {
  return {
    type: "canvas",
    projectId: "p1",
    processId: "pr1",
    processName: "Idem",
    bpmnModelId: "m1",
    currentBpmnXml: xml,
  };
}

describe("EmptyState", () => {
  it("suggests building the model while the canvas is still empty", () => {
    render(<EmptyState scope={canvasScope(EMPTY_CANVAS)} onSelectPrompt={vi.fn()} />);

    // CANVAS-V2-01: proporre una modifica a un modello che non esiste ancora
    // significa raccontare al consulente un processo che nessuna fonte descrive.
    expect(screen.getByText("scope.canvas.prompts")).toBeInTheDocument();
    expect(screen.queryByText("scope.canvas.promptsModeled")).not.toBeInTheDocument();
  });

  it("switches to model-level prompts once the canvas carries flow nodes", () => {
    render(<EmptyState scope={canvasScope(MODELLED_CANVAS)} onSelectPrompt={vi.fn()} />);

    expect(screen.getByText("scope.canvas.promptsModeled")).toBeInTheDocument();
  });

  it("treats a missing canvas XML as an empty canvas", () => {
    render(<EmptyState scope={canvasScope(null)} onSelectPrompt={vi.fn()} />);

    expect(screen.getByText("scope.canvas.prompts")).toBeInTheDocument();
  });

  it("keeps a single prompt set outside the canvas", () => {
    render(<EmptyState scope={{ type: "consultant" }} onSelectPrompt={vi.fn()} />);

    expect(screen.getByText("scope.consultant.prompts")).toBeInTheDocument();
  });
});
