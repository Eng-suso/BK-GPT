import { useTranslation } from "react-i18next";
import { ClipboardCheck, X } from "lucide-react";

import { Button } from "@/ui/button";
import type { BpmnReview } from "../types";

export type ModelingWorkspaceBarProps = {
  /** Il piano persistito, o `null` quando il processo non ne ha ancora uno. */
  review: BpmnReview | null;
  /** La prima lettura del piano non e' ancora tornata. */
  isLoadingReview?: boolean;
  /** La lettura del piano e' fallita: non si sa se un piano esista. */
  reviewError?: string | null;
  /** Se questo scope puo' essere modellato (processo o canvas). */
  canModel: boolean;
  /** Il turno e' in corso: la modellazione non si riavvia a meta'. */
  isBusy: boolean;
  onOpenReview: () => void;
  /** Attivazione esplicita: la modellazione parte solo da qui o da una richiesta scritta. */
  onStartModeling: () => void;
  /** Chiude la superficie: la chat resta utilizzabile, il piano resta dov'e'. */
  onDismiss: () => void;
  openButtonRef?: React.Ref<HTMLButtonElement>;
};

/**
 * La superficie di modellazione, fuori dalla conversazione.
 *
 * Il workflow di modellazione stava incollato al transcript: la card di
 * readiness, il questionario e la review restavano attaccati ai messaggi e
 * scorrevano con loro per sempre. Una decisione presa tre giorni fa continuava a
 * chiedere di essere presa, e la chat non tornava piu' a essere una chat.
 *
 * Qui la modellazione e' una superficie con un ciclo di vita: si apre quando il
 * consulente la attiva, si chiude, si riapre, e cio' che contiene vive nel piano
 * persistito - non nel transcript. Chiuderla non perde niente, perche' non c'e'
 * niente qui che non sia gia' nel piano.
 *
 * Lo stato che mostra viene dal piano riletto dal backend, mai da uno stato
 * locale che potrebbe divergerne: e' la stessa regola per cui il Canvas non
 * tiene una seconda versione della verita' del processo.
 */
export function ModelingWorkspaceBar({
  review,
  isLoadingReview = false,
  reviewError = null,
  canModel,
  isBusy,
  onOpenReview,
  onStartModeling,
  onDismiss,
  openButtonRef,
}: ModelingWorkspaceBarProps) {
  const { t } = useTranslation("chat");
  if (!canModel) return null;

  const openQuestions = (review?.open_questions ?? []).filter((item) => !item.answer);
  const needsDecision = openQuestions.length > 0;
  // Tre stati collassavano in uno. `review === null` significava "sto leggendo",
  // "la lettura e' fallita" e "il processo non ha un piano", e la barra diceva
  // sempre la terza: un'affermazione sullo stato persistito fatta senza averlo
  // letto, con accanto un bottone che propone di costruire un piano che potrebbe
  // esistere - e costruirlo lo sovrascriverebbe.
  const planStateUnknown = !review && (isLoadingReview || Boolean(reviewError));

  return (
    <div
      className="modeling-workspace-bar"
      role="region"
      aria-label={t("modeling.label")}
    >
      <div className="modeling-workspace-text">
        <p className="modeling-workspace-title">
          {planStateUnknown
            ? reviewError
              ? t("modeling.planUnreadable")
              : t("modeling.rereading")
            : review
              ? needsDecision
                ? openQuestions.length === 1
                  ? t("modeling.oneDecision")
                  : t("modeling.manyDecisions", { count: openQuestions.length })
                : t("modeling.available")
              : t("modeling.modelling")}
        </p>
        <p className="modeling-workspace-detail">
          {planStateUnknown
            ? (reviewError ??
              t("modeling.rereadingDetail"))
            : review
              ? // La versione del piano e' il dato che rende verificabile "il piano
                // e' aggiornato": senza, e' un'affermazione senza referente, e il
                // consulente non ha modo di sapere se sta guardando cio' che ha
                // appena chiesto di scrivere o la versione di prima.
                t("modeling.planVersion", { version: review.version })
              : t("modeling.startHint")}
        </p>
      </div>

      {planStateUnknown ? null : review ? (
        <Button
          ref={openButtonRef}
          type="button"
          size="sm"
          variant={needsDecision ? "default" : "outline"}
          onClick={onOpenReview}
        >
          <ClipboardCheck aria-hidden="true" />
          {t(needsDecision ? "modeling.decide" : "modeling.open")}
        </Button>
      ) : (
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={isBusy}
          onClick={onStartModeling}
        >
          <ClipboardCheck aria-hidden="true" />
          {t("modeling.draft")}
        </Button>
      )}

      <Button
        type="button"
        size="sm"
        variant="ghost"
        aria-label={t("modeling.dismiss")}
        onClick={onDismiss}
      >
        <X aria-hidden="true" />
      </Button>
    </div>
  );
}
