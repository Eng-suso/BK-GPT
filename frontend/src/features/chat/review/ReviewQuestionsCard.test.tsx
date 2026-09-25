import type { ReactNode } from "react";
import { I18nextProvider } from "react-i18next";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { render as rtlRender, screen } from "@testing-library/react";
import { setupUser } from "@/test/user";
import { i18n } from "@/lib/i18n";

import { ReviewQuestionsCard } from "./ReviewQuestionsCard";
import { sortQuestions } from "./questionOrder";
import type { ReviewOpenQuestion } from "../types";

const sortedTopics = (questions: ReviewOpenQuestion[]): string[] =>
  sortQuestions(questions).map((item) => item.affects ?? "");

const question = (overrides: Partial<ReviewOpenQuestion> = {}): ReviewOpenQuestion => ({
  question_id: "chi-approva",
  question: "Chi approva un ordine oltre 10k?",
  severity: "blocking",
  options: [
    { label: "Direzione amministrativa", implication: "Aggiunge un passaggio di approvazione" },
    { label: "Il responsabile commerciale", implication: "L'approvazione resta dentro Sales" },
  ],
  answer: null,
  ...overrides,
});

/**
 * La carta parla adesso da i18next: senza il provider, `t` restituisce la
 * chiave e il test verificherebbe una stringa che nessuno legge.
 */
function render(ui: ReactNode) {
  return rtlRender(<I18nextProvider i18n={i18n}>{ui}</I18nextProvider>);
}

describe("ReviewQuestionsCard", () => {
  beforeAll(async () => {
    await i18n.changeLanguage("it");
  });

  it("offers the alternatives the agent proposed, with what each would change", () => {
    render(
      <ReviewQuestionsCard questions={[question()]} isAnswering={false} onAnswer={vi.fn()} />,
    );

    expect(screen.getByRole("button", { name: /Direzione amministrativa/ })).toBeInTheDocument();
    expect(screen.getByText("Aggiunge un passaggio di approvazione")).toBeInTheDocument();
  });

  it("answers with the option the consultant picked", async () => {
    const user = setupUser();
    const onAnswer = vi.fn().mockResolvedValue(undefined);
    render(
      <ReviewQuestionsCard questions={[question()]} isAnswering={false} onAnswer={onAnswer} />,
    );

    await user.click(screen.getByRole("button", { name: /Direzione amministrativa/ }));

    expect(onAnswer).toHaveBeenCalledWith(
      "Chi approva un ordine oltre 10k?",
      "Direzione amministrativa",
    );
  });

  it("numbers the alternatives in the order the agent proposed them, Altro last", () => {
    render(
      <ReviewQuestionsCard questions={[question()]} isAnswering={false} onAnswer={vi.fn()} />,
    );

    const choices = screen
      .getAllByRole("button")
      .map((node) => node.textContent?.replace(/\s+/g, " ").trim());

    expect(choices[0]).toMatch(/^1 ?Direzione amministrativa/);
    expect(choices[1]).toMatch(/^2 ?Il responsabile commerciale/);
    // "Altro" chiude sempre l'elenco: e' l'ultima scelta, non un ripiego fuori lista.
    expect(choices.at(-1)).toMatch(/^3 ?Altro/);
  });

  it("picks an alternative with its number key", async () => {
    const user = setupUser();
    const onAnswer = vi.fn().mockResolvedValue(undefined);
    render(
      <ReviewQuestionsCard questions={[question()]} isAnswering={false} onAnswer={onAnswer} />,
    );

    await user.click(screen.getByRole("button", { name: /Direzione amministrativa/ }));
    onAnswer.mockClear();
    await user.keyboard("2");

    expect(onAnswer).toHaveBeenCalledWith(
      "Chi approva un ordine oltre 10k?",
      "Il responsabile commerciale",
    );
  });

  it("always leaves a way to answer in your own words", async () => {
    // A proposed option that does not fit must never be the only way to answer.
    const user = setupUser();
    const onAnswer = vi.fn().mockResolvedValue(undefined);
    render(
      <ReviewQuestionsCard questions={[question()]} isAnswering={false} onAnswer={onAnswer} />,
    );

    await user.click(screen.getByRole("button", { name: /Altro/ }));
    await user.type(screen.getByRole("textbox"), "Dipende dall'importo");
    await user.click(screen.getByRole("button", { name: /Rispondi/ }));

    expect(onAnswer).toHaveBeenCalledWith(
      "Chi approva un ordine oltre 10k?",
      "Dipende dall'importo",
    );
  });

  it("still asks a question that came without alternatives", async () => {
    const user = setupUser();
    const onAnswer = vi.fn().mockResolvedValue(undefined);
    render(
      <ReviewQuestionsCard
        questions={[question({ options: [] })]}
        isAnswering={false}
        onAnswer={onAnswer}
      />,
    );

    expect(screen.getByText("Chi approva un ordine oltre 10k?")).toBeInTheDocument();
    // Senza alternative proposte "Altro" e' la prima e unica scelta.
    await user.click(screen.getByRole("button", { name: /Altro/ }));
    await user.type(screen.getByRole("textbox"), "Il direttore di filiale");
    await user.click(screen.getByRole("button", { name: /Rispondi/ }));

    expect(onAnswer).toHaveBeenCalledWith(
      "Chi approva un ordine oltre 10k?",
      "Il direttore di filiale",
    );
  });

  it("hides questions that have already been decided", () => {
    const { container } = render(
      <ReviewQuestionsCard
        questions={[question({ answer: "Direzione amministrativa" })]}
        isAnswering={false}
        onAnswer={vi.fn()}
      />,
    );

    // Nothing left to decide means no card at all, not an empty one.
    expect(container).toBeEmptyDOMElement();
  });

  it("puts blocking gaps first", () => {
    render(
      <ReviewQuestionsCard
        questions={[
          question({ question_id: "b", question: "Domanda minore", severity: "non_blocking", options: [] }),
          question({ question_id: "a", question: "Domanda bloccante", severity: "blocking", options: [] }),
        ]}
        isAnswering={false}
        onAnswer={vi.fn()}
      />,
    );

    const asked = screen.getAllByRole("listitem").map((node) => node.textContent);
    expect(asked[0]).toContain("Domanda bloccante");
    // La numerazione segue l'ordine mostrato, non quello di arrivo: e' il numero
    // che il consulente preme.
    expect(asked[0]).toMatch(/^1/);
  });

  it("asks one question at a time and starts from the part of the model that is blocked", () => {
    // L'ordine non viene piu' da una lista di parole chiave applicata al testo
    // della domanda - quella era una checklist statica che metteva "qual e' il
    // trigger?" in cima anche dopo tre interviste che il trigger lo avevano
    // detto. Viene da cosa la domanda tocca e da quanto blocca il disegno.
    render(
      <ReviewQuestionsCard
        questions={[
          question({
            question_id: "etichetta",
            question: "Come si chiama il documento finale?",
            affects: "etichetta di un task",
            severity: "non_blocking",
          }),
          question({
            question_id: "regolarizzazione",
            question: "Chi regolarizza l'ordine urgente di Manutenzione?",
            affects: "percorso urgente",
            severity: "blocking",
          }),
        ]}
        isAnswering={false}
        onAnswer={vi.fn()}
      />,
    );

    expect(
      screen.getByText("Chi regolarizza l'ordine urgente di Manutenzione?"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Come si chiama il documento finale?"),
    ).not.toBeInTheDocument();
  });

  it("keeps questions about the same part of the model together", () => {
    const asked = sortedTopics([
      question({ question_id: "a", affects: "percorso urgente", severity: "blocking" }),
      question({ question_id: "b", affects: "corsia di Acquisti", severity: "non_blocking" }),
      question({ question_id: "c", affects: "percorso urgente", severity: "non_blocking" }),
    ]);

    // Il gruppo che contiene la bloccante viene prima e non si spezza: al
    // consulente arriva un argomento alla volta, non cinque domande scollegate.
    expect(asked).toEqual([
      "percorso urgente",
      "percorso urgente",
      "corsia di Acquisti",
    ]);
  });

  it("shows the evidence gap the question comes from", () => {
    render(
      <ReviewQuestionsCard
        questions={[
          question({
            grounded_in:
              "Paolo descrive un via libera del responsabile per alcuni importi, Francesca dice che l'autorizzazione serve sempre.",
          }),
        ]}
        isAnswering={false}
        onAnswer={vi.fn()}
      />,
    );

    expect(
      screen.getByText(/Paolo descrive un via libera del responsabile/),
    ).toBeInTheDocument();
  });

  it("caps proposed choices at four and keeps Altro available", () => {
    render(
      <ReviewQuestionsCard
        questions={[question({
          options: [
            { label: "A", implication: "a" },
            { label: "B", implication: "b" },
            { label: "C", implication: "c" },
            { label: "D", implication: "d" },
            { label: "E", implication: "e" },
          ],
        })]}
        isAnswering={false}
        onAnswer={vi.fn()}
      />,
    );

    expect(screen.getAllByRole("button")).toHaveLength(5);
    expect(screen.queryByRole("button", { name: /E/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Altro/ })).toBeInTheDocument();
  });

  it("cannot answer twice while the first answer is in flight", async () => {
    const user = setupUser();
    const onAnswer = vi.fn().mockResolvedValue(undefined);
    render(
      <ReviewQuestionsCard questions={[question()]} isAnswering onAnswer={onAnswer} />,
    );

    await user.click(screen.getByRole("button", { name: /Direzione amministrativa/ }));

    expect(onAnswer).not.toHaveBeenCalled();
  });
});
