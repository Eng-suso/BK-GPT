import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ReviewQuestionsCard } from "./ReviewQuestionsCard";
import type { ReviewOpenQuestion } from "../types";

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

describe("ReviewQuestionsCard", () => {
  it("offers the alternatives the agent proposed, with what each would change", () => {
    render(
      <ReviewQuestionsCard questions={[question()]} isAnswering={false} onAnswer={vi.fn()} />,
    );

    expect(screen.getByRole("button", { name: /Direzione amministrativa/ })).toBeInTheDocument();
    expect(screen.getByText("Aggiunge un passaggio di approvazione")).toBeInTheDocument();
  });

  it("answers with the option the consultant picked", async () => {
    const user = userEvent.setup();
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

  it("always leaves a way to answer in your own words", async () => {
    // A proposed option that does not fit must never be the only way to answer.
    const user = userEvent.setup();
    const onAnswer = vi.fn().mockResolvedValue(undefined);
    render(
      <ReviewQuestionsCard questions={[question()]} isAnswering={false} onAnswer={onAnswer} />,
    );

    await user.click(screen.getByRole("button", { name: /Nessuna di queste/ }));
    await user.type(screen.getByRole("textbox"), "Dipende dall'importo");
    await user.click(screen.getByRole("button", { name: /Rispondi/ }));

    expect(onAnswer).toHaveBeenCalledWith(
      "Chi approva un ordine oltre 10k?",
      "Dipende dall'importo",
    );
  });

  it("still asks a question that came without alternatives", () => {
    render(
      <ReviewQuestionsCard
        questions={[question({ options: [] })]}
        isAnswering={false}
        onAnswer={vi.fn()}
      />,
    );

    expect(screen.getByText("Chi approva un ordine oltre 10k?")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Rispondi" })).toBeInTheDocument();
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

    const asked = screen.getAllByRole("article").map((node) => node.textContent);
    expect(asked[0]).toContain("Domanda bloccante");
  });

  it("cannot answer twice while the first answer is in flight", async () => {
    const user = userEvent.setup();
    const onAnswer = vi.fn().mockResolvedValue(undefined);
    render(
      <ReviewQuestionsCard questions={[question()]} isAnswering onAnswer={onAnswer} />,
    );

    await user.click(screen.getByRole("button", { name: /Direzione amministrativa/ }));

    expect(onAnswer).not.toHaveBeenCalled();
  });
});
