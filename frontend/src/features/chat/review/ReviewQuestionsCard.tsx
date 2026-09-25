import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { CornerDownLeft, HelpCircle, Check } from "lucide-react";

import { Button } from "@/ui/button";
import { cn } from "@/lib/utils";
import type { ReviewOpenQuestion } from "../types";
import { sortQuestions } from "./questionOrder";

type ReviewQuestionsCardProps = {
  questions: ReviewOpenQuestion[];
  isAnswering: boolean;
  onAnswer: (question: string, answer: string) => Promise<void>;
};

/** Oltre questa posizione la scorciatoia numerica non esiste piu' sulla tastiera. */
const MAX_SHORTCUT_INDEX = 9;

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
  const { t } = useTranslation("chat");
  const open = sortQuestions(questions.filter((item) => !item.answer));
  if (open.length === 0) return null;
  const current = open[0];

  return (
    <section className="review-questions-card" aria-label={t("questions.title")}>
      <header className="review-questions-header">
        <span className="review-questions-icon" aria-hidden="true">
          <HelpCircle className="size-4" />
        </span>
        <div>
          <p className="product-eyebrow">{t("questions.decisionNeeded")}</p>
          <h4>{t("questions.oneAtATime")}</h4>
          <p>{open.length === 1 ? t("questions.lastOpen") : t("questions.openPoints", { count: open.length })}</p>
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
  const { t } = useTranslation("chat");
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

  const topic = (question.affects ?? "").trim();
  const grounding = (question.grounded_in ?? "").trim();

  return (
    <li className="review-question">
      {topic ? (
        <p className="review-question-topic">Cosa cambia nel modello: {topic}</p>
      ) : null}
      <p className="review-question-text" id={labelId}>
        <span className="review-question-position">
          {position}
          <span className="sr-only">{t("questions.ofTotal", { total })}</span>.
        </span>
        {question.severity === "blocking" ? (
          <span className="review-question-badge">{t("questions.blocking")}</span>
        ) : null}
        {question.question}
      </p>

      {/* Perche' la domanda esiste. Senza, "chi approva?" e' indistinguibile da
          quella che si farebbe prima di aver sentito qualcuno; con, il
          consulente vede che due voci dicono cose diverse e decide su quelle. */}
      {grounding ? <p className="review-question-grounding">{grounding}</p> : null}

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
              {t("questions.other")}
            </span>
            <small>
              {options.length > 0
                ? t("questions.noneOfThese")
                : t("questions.writeAnswer")}
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
            {t("questions.ownLabel")}
          </label>
          <input
            id={`${labelId}-own`}
            ref={ownInputRef}
            type="text"
            value={ownAnswer}
            placeholder={t("questions.placeholder")}
            onChange={(event) => setOwnAnswer(event.target.value)}
            disabled={isAnswering}
          />
          <Button type="submit" size="sm" disabled={!ownAnswer.trim() || isAnswering}>
            <CornerDownLeft aria-hidden="true" />
            <span>{t("questions.submit")}</span>
          </Button>
        </form>
      ) : null}
    </li>
  );
}
