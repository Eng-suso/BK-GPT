import { useState } from "react";
import { CornerDownLeft, HelpCircle, Check } from "lucide-react";

import { Button } from "@/ui/button";
import { cn } from "@/lib/utils";
import type { ReviewOpenQuestion } from "../types";

type ReviewQuestionsCardProps = {
  questions: ReviewOpenQuestion[];
  isAnswering: boolean;
  onAnswer: (question: string, answer: string) => Promise<void>;
};

/** Blocking gaps first: they are the ones that keep the plan from being drawn. */
const SEVERITY_ORDER: Record<string, number> = {
  blocking: 0,
  non_blocking: 1,
  optional_extension: 2,
};

function sortQuestions(questions: ReviewOpenQuestion[]): ReviewOpenQuestion[] {
  return [...questions].sort(
    (a, b) =>
      (SEVERITY_ORDER[a.severity ?? "non_blocking"] ?? 1) -
      (SEVERITY_ORDER[b.severity ?? "non_blocking"] ?? 1),
  );
}

/**
 * The plan's open gaps, as questions the consultant can actually close.
 *
 * The alternatives come from the agent - it has the process in front of it -
 * and there is always a way out to your own words: a proposed option that does
 * not fit must never be the only way to answer.
 */
export function ReviewQuestionsCard({
  questions,
  isAnswering,
  onAnswer,
}: ReviewQuestionsCardProps) {
  const open = sortQuestions(questions.filter((item) => !item.answer));
  if (open.length === 0) return null;

  return (
    <section className="review-questions-card" aria-label="Domande aperte sul piano">
      <header className="review-questions-header">
        <span className="review-questions-icon" aria-hidden="true">
          <HelpCircle className="size-4" />
        </span>
        <div>
          <p className="product-eyebrow">Serve una tua decisione</p>
          <h4>
            {open.length === 1
              ? "1 punto da chiarire prima di disegnare"
              : `${open.length} punti da chiarire prima di disegnare`}
          </h4>
        </div>
      </header>

      <div className="review-questions-list">
        {open.map((question) => (
          <OpenQuestion
            key={question.question_id}
            question={question}
            isAnswering={isAnswering}
            onAnswer={onAnswer}
          />
        ))}
      </div>
    </section>
  );
}

function OpenQuestion({
  question,
  isAnswering,
  onAnswer,
}: {
  question: ReviewOpenQuestion;
  isAnswering: boolean;
  onAnswer: (question: string, answer: string) => Promise<void>;
}) {
  const [isWritingOwn, setIsWritingOwn] = useState(false);
  const [ownAnswer, setOwnAnswer] = useState("");
  const [pending, setPending] = useState<string | null>(null);
  const options = question.options ?? [];
  const labelId = `question-${question.question_id}`;

  const answer = async (value: string) => {
    const clean = value.trim();
    if (!clean || isAnswering) return;
    setPending(clean);
    try {
      await onAnswer(question.question, clean);
    } finally {
      setPending(null);
    }
  };

  return (
    <article className="review-question">
      <p className="review-question-text" id={labelId}>
        {question.severity === "blocking" ? (
          <span className="review-question-badge">Bloccante</span>
        ) : null}
        {question.question}
      </p>

      {options.length > 0 ? (
        <div className="review-question-options" role="group" aria-labelledby={labelId}>
          {options.map((option) => (
            <button
              key={option.label}
              type="button"
              className={cn(
                "review-question-option",
                pending === option.label && "is-pending",
              )}
              disabled={isAnswering}
              onClick={() => void answer(option.label)}
            >
              <span className="review-question-option-label">
                {pending === option.label ? (
                  <Check className="size-3.5" aria-hidden="true" />
                ) : null}
                {option.label}
              </span>
              {option.implication ? <small>{option.implication}</small> : null}
            </button>
          ))}
        </div>
      ) : null}

      {isWritingOwn ? (
        <form
          className="review-question-own"
          onSubmit={(event) => {
            event.preventDefault();
            void answer(ownAnswer);
          }}
        >
          <label className="sr-only" htmlFor={`${labelId}-own`}>
            Rispondi con parole tue
          </label>
          <input
            id={`${labelId}-own`}
            type="text"
            value={ownAnswer}
            autoFocus
            placeholder="Rispondi con parole tue…"
            onChange={(event) => setOwnAnswer(event.target.value)}
            disabled={isAnswering}
          />
          <Button type="submit" size="sm" disabled={!ownAnswer.trim() || isAnswering}>
            <CornerDownLeft aria-hidden="true" />
            <span>Rispondi</span>
          </Button>
        </form>
      ) : (
        <button
          type="button"
          className="review-question-escape"
          onClick={() => setIsWritingOwn(true)}
        >
          {options.length > 0 ? "Nessuna di queste — rispondo io" : "Rispondi"}
        </button>
      )}
    </article>
  );
}
