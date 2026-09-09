import { useRef, useState } from "react";
import { CornerDownLeft, HelpCircle, Check } from "lucide-react";

import { Button } from "@/ui/button";
import { cn } from "@/lib/utils";
import type { ReviewOpenQuestion } from "../types";

type ReviewQuestionsCardProps = {
  questions: ReviewOpenQuestion[];
  isAnswering: boolean;
  onAnswer: (question: string, answer: string) => Promise<void>;
};

/** Process dependency order comes before severity. */
const DEPENDENCY_PATTERNS: RegExp[] = [
  /trigger|avvia|inizia|evento iniziale|cosa fa partire/i,
  /prima attivit|primo passaggio|prima azione/i,
  /attore|ruolo|chi (?:esegue|riceve|gestisce|avvia)/i,
  /decision|approv|condizion|gateway|soglia/i,
  /esito|fine|termina|risultato|output/i,
];

const SEVERITY_ORDER: Record<string, number> = {
  blocking: 0,
  non_blocking: 1,
  optional_extension: 2,
};

/** Oltre questa posizione la scorciatoia numerica non esiste piu' sulla tastiera. */
const MAX_SHORTCUT_INDEX = 9;

/**
 * Sorts review questions by severity without modifying the input array.
 *
 * @param questions - The review questions to sort
 * @returns A new array ordered from blocking to optional
 */
function sortQuestions(questions: ReviewOpenQuestion[]): ReviewOpenQuestion[] {
  const dependency = (question: ReviewOpenQuestion) => {
    const index = DEPENDENCY_PATTERNS.findIndex((pattern) => pattern.test(question.question));
    return index === -1 ? DEPENDENCY_PATTERNS.length : index;
  };
  return [...questions].sort((a, b) =>
    dependency(a) - dependency(b) ||
    (SEVERITY_ORDER[a.severity ?? "non_blocking"] ?? 1) -
      (SEVERITY_ORDER[b.severity ?? "non_blocking"] ?? 1),
  );
}

/**
 * Displays unanswered plan questions that require the consultant's decisions.
 *
 * @param questions - Plan questions to review.
 * @returns The review questions card, or `null` when all questions have been answered.
 */
export function ReviewQuestionsCard({
  questions,
  isAnswering,
  onAnswer,
}: ReviewQuestionsCardProps) {
  const open = sortQuestions(questions.filter((item) => !item.answer));
  if (open.length === 0) return null;
  const current = open[0];

  return (
    <section className="review-questions-card" aria-label="Domande aperte sul piano">
      <header className="review-questions-header">
        <span className="review-questions-icon" aria-hidden="true">
          <HelpCircle className="size-4" />
        </span>
        <div>
          <p className="product-eyebrow">Serve una tua decisione</p>
          <h4>Una decisione alla volta</h4>
          <p>{open.length === 1 ? "Ultimo punto aperto" : `${open.length} punti aperti`}</p>
        </div>
      </header>

      <ol className="review-questions-list">
        <OpenQuestion
          key={current.question_id}
          position={1}
          total={open.length}
          question={current}
          isAnswering={isAnswering}
          onAnswer={onAnswer}
        />
      </ol>
    </section>
  );
}

/**
 * Presents an unanswered review question and collects a response.
 *
 * Le alternative sono numerate nell'ordine in cui l'agente le ha proposte, e
 * l'ultima voce e' sempre "Altro": una domanda a scelta chiusa che non prevede
 * la risposta vera del consulente lo costringe a scegliere il meno sbagliato, e
 * quella scelta finisce nel piano come se fosse la sua.
 *
 * @param question - The question, proposed answers, and severity to display.
 * @param position - Where this question sits in the visible list.
 * @param total - How many questions are open, for the "n di m" label.
 * @param isAnswering - Whether answer submission is currently in progress.
 * @param onAnswer - Handles the submitted question answer.
 */
function OpenQuestion({
  question,
  position,
  total,
  isAnswering,
  onAnswer,
}: {
  question: ReviewOpenQuestion;
  position: number;
  total: number;
  isAnswering: boolean;
  onAnswer: (question: string, answer: string) => Promise<void>;
}) {
  const [isWritingOwn, setIsWritingOwn] = useState(false);
  const [ownAnswer, setOwnAnswer] = useState("");
  const [pending, setPending] = useState<string | null>(null);
  const ownInputRef = useRef<HTMLInputElement>(null);
  const options = (question.options ?? []).slice(0, 4);
  const labelId = `question-${question.question_id}`;
  const otherIndex = options.length + 1;

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

  const openOwnAnswer = () => {
    setIsWritingOwn(true);
    // Il focus segue la scelta: chi ha appena premuto "Altro" con la tastiera
    // deve trovarsi nel campo, non doverlo cercare con Tab.
    window.requestAnimationFrame(() => ownInputRef.current?.focus());
  };

  /** Le scorciatoie numeriche del gruppo: 1..n sulle opzioni, n+1 su "Altro". */
  const selectByDigit = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (isAnswering || event.metaKey || event.ctrlKey || event.altKey) return;
    const digit = Number(event.key);
    if (!Number.isInteger(digit) || digit < 1 || digit > MAX_SHORTCUT_INDEX) return;
    if (digit === otherIndex) {
      event.preventDefault();
      openOwnAnswer();
      return;
    }
    const option = options[digit - 1];
    if (!option) return;
    event.preventDefault();
    void answer(option.label);
  };

  return (
    <li className="review-question">
      <p className="review-question-text" id={labelId}>
        <span className="review-question-position">
          {position}
          <span className="sr-only"> di {total}</span>.
        </span>
        {question.severity === "blocking" ? (
          <span className="review-question-badge">Bloccante</span>
        ) : null}
        {question.question}
      </p>

      <div
        className="review-question-options"
        role="group"
        aria-labelledby={labelId}
        onKeyDown={selectByDigit}
      >
        {options.map((option, index) => (
          <button
            key={option.label}
            type="button"
            className={cn(
              "review-question-option",
              pending === option.label && "is-pending",
            )}
            disabled={isAnswering}
            aria-keyshortcuts={index + 1 <= MAX_SHORTCUT_INDEX ? String(index + 1) : undefined}
            onClick={() => void answer(option.label)}
          >
            <span className="review-question-option-label">
              <span className="review-question-option-index" aria-hidden="true">
                {index + 1}
              </span>
              {pending === option.label ? (
                <Check className="size-3.5" aria-hidden="true" />
              ) : null}
              {option.label}
            </span>
            {option.implication ? <small>{option.implication}</small> : null}
          </button>
        ))}

        {isWritingOwn ? null : (
          <button
            type="button"
            className="review-question-option review-question-option-other"
            disabled={isAnswering}
            aria-keyshortcuts={
              otherIndex <= MAX_SHORTCUT_INDEX ? String(otherIndex) : undefined
            }
            onClick={openOwnAnswer}
          >
            <span className="review-question-option-label">
              <span className="review-question-option-index" aria-hidden="true">
                {otherIndex}
              </span>
              Altro
            </span>
            <small>
              {options.length > 0
                ? "Nessuna di queste: scrivi la risposta giusta"
                : "Scrivi la risposta"}
            </small>
          </button>
        )}
      </div>

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
            ref={ownInputRef}
            type="text"
            value={ownAnswer}
            placeholder="Rispondi con parole tue…"
            onChange={(event) => setOwnAnswer(event.target.value)}
            disabled={isAnswering}
          />
          <Button type="submit" size="sm" disabled={!ownAnswer.trim() || isAnswering}>
            <CornerDownLeft aria-hidden="true" />
            <span>Rispondi</span>
          </Button>
        </form>
      ) : null}
    </li>
  );
}
