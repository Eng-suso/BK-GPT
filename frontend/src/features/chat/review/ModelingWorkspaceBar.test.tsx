import type { ReactNode } from "react";
import { I18nextProvider } from "react-i18next";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { render as rtlRender, screen } from "@testing-library/react";
import { setupUser } from "@/test/user";
import { i18n } from "@/lib/i18n";

import { ModelingWorkspaceBar } from "./ModelingWorkspaceBar";
import type { BpmnReview } from "../types";

const review = (overrides: Partial<BpmnReview> = {}): BpmnReview =>
  ({
    bpmn_model_id: "bpmn-1",
    process_id: "proc-1",
    version: 3,
    bpmn_brief: "# Piano",
    readiness_score: 6,
    created_at: "2026-09-09T10:00:00Z",
    updated_at: "2026-09-09T10:00:00Z",
    open_questions: [],
    ...overrides,
  }) as BpmnReview;

const props = {
  canModel: true,
  isBusy: false,
  onOpenReview: vi.fn(),
  onStartModeling: vi.fn(),
  onDismiss: vi.fn(),
};

/**
 * La barra parla adesso da i18next: senza il provider, `t` restituisce la
 * chiave e il test verificherebbe una stringa che nessuno legge.
 */
function render(ui: ReactNode) {
  return rtlRender(<I18nextProvider i18n={i18n}>{ui}</I18nextProvider>);
}

describe("ModelingWorkspaceBar", () => {
  beforeAll(async () => {
    await i18n.changeLanguage("it");
  });

  it("stays out of the way where the process cannot be modelled", () => {
    const { container } = render(
      <ModelingWorkspaceBar {...props} review={null} canModel={false} />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it("does not open the modeling workspace on its own", async () => {
    // Il BPMN parte da un gesto del consulente. Un turno che ha solo riassunto
    // le evidenze non deve aprire niente: la barra offre, non entra.
    const onStartModeling = vi.fn();
    render(
      <ModelingWorkspaceBar {...props} review={null} onStartModeling={onStartModeling} />,
    );

    expect(screen.getByRole("button", { name: /Genera bozza/ })).toBeInTheDocument();
    expect(onStartModeling).not.toHaveBeenCalled();
  });

  it("activates modeling only when asked", async () => {
    const user = setupUser();
    const onStartModeling = vi.fn();
    render(
      <ModelingWorkspaceBar {...props} review={null} onStartModeling={onStartModeling} />,
    );

    await user.click(screen.getByRole("button", { name: /Genera bozza/ }));

    expect(onStartModeling).toHaveBeenCalledOnce();
  });

  it("says how many decisions the plan is waiting for", () => {
    render(
      <ModelingWorkspaceBar
        {...props}
        review={review({
          open_questions: [
            { question_id: "a", question: "Chi regolarizza?", answer: null },
            { question_id: "b", question: "Quale documento?", answer: null },
            { question_id: "c", question: "Gia' deciso", answer: "Acquisti" },
          ],
        })}
      />,
    );

    expect(screen.getByText("Servono 2 tue decisioni")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Decidi/ })).toBeInTheDocument();
  });

  it("does not claim there is no plan while the plan is still being read", () => {
    // "Nessun piano" e' un'affermazione sullo stato persistito: farla mentre la
    // lettura e' in corso, e offrire di costruirne uno, e' come dichiarare
    // salvato cio' che non si e' riletto - con il rischio in piu' di
    // sovrascrivere un piano che esiste.
    render(<ModelingWorkspaceBar {...props} review={null} isLoadingReview />);

    expect(screen.queryByRole("button", { name: /Genera bozza/ })).not.toBeInTheDocument();
    expect(screen.getByText("Rileggo il piano")).toBeInTheDocument();
  });

  it("says the plan could not be read instead of saying there is none", () => {
    render(
      <ModelingWorkspaceBar
        {...props}
        review={null}
        reviewError="Non è stato possibile rileggere il piano."
      />,
    );

    expect(screen.getByText("Piano non leggibile")).toBeInTheDocument();
    expect(
      screen.getByText("Non è stato possibile rileggere il piano."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Genera bozza/ })).not.toBeInTheDocument();
  });

  it("names the plan version it is showing", () => {
    // "Il piano e' aggiornato" senza dire quale versione e' un'affermazione che
    // il consulente non puo' verificare.
    render(<ModelingWorkspaceBar {...props} review={review({ version: 7 })} />);

    expect(screen.getByText(/Piano V7/)).toBeInTheDocument();
  });

  it("can be closed without losing the plan", async () => {
    const user = setupUser();
    const onDismiss = vi.fn();
    render(<ModelingWorkspaceBar {...props} review={review()} onDismiss={onDismiss} />);

    await user.click(
      screen.getByRole("button", { name: /Chiudi il workspace di modellazione/ }),
    );

    // Chiudere la superficie e' un gesto sulla vista, non sul piano: nessuna
    // scrittura parte da qui.
    expect(onDismiss).toHaveBeenCalledOnce();
    expect(props.onOpenReview).not.toHaveBeenCalled();
  });
});
