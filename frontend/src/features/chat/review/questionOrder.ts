import type { ReviewOpenQuestion } from "../types";

const SEVERITY_ORDER: Record<string, number> = {
  blocking: 0,
  non_blocking: 1,
  optional_extension: 2,
};

/**
 * Ordina le domande sulle dipendenze reali della modellazione.
 *
 * L'ordine veniva da una lista di espressioni regolari - trigger, prima
 * attivita', attore, decisione, esito - applicate al testo della domanda: una
 * checklist statica travestita da priorita'. Metteva in cima "qual e' il
 * trigger?" anche quando le interviste il trigger lo avevano gia' detto, e
 * spingeva in fondo una lacuna vera che nominava un caso concreto.
 *
 * Qui l'ordine viene da due cose che il piano dichiara: `severity`, cioe' se
 * senza quella risposta la topologia non si puo' disegnare, e `affects`, cioe'
 * quale parte del modello la domanda tocca. Le domande che toccano la stessa
 * parte restano consecutive, cosi' al consulente arriva un argomento alla volta
 * invece di cinque domande scollegate.
 *
 * @param questions - Le domande aperte del piano.
 * @returns Un nuovo array, dalle bloccanti alle opzionali, raggruppato per parte toccata.
 */
export function sortQuestions(questions: ReviewOpenQuestion[]): ReviewOpenQuestion[] {
  const severity = (question: ReviewOpenQuestion) =>
    SEVERITY_ORDER[question.severity ?? "non_blocking"] ?? 1;
  const topic = (question: ReviewOpenQuestion) =>
    (question.affects ?? "").trim().toLocaleLowerCase();

  // L'argomento eredita la priorita' della sua domanda piu' urgente: un gruppo
  // che contiene una bloccante viene prima, e non si spezza.
  const topicRank = new Map<string, number>();
  questions.forEach((question) => {
    const key = topic(question);
    const rank = Math.min(topicRank.get(key) ?? Number.POSITIVE_INFINITY, severity(question));
    topicRank.set(key, rank);
  });
  const topicOrder = [...new Set(questions.map(topic))];

  return [...questions].sort(
    (a, b) =>
      (topicRank.get(topic(a)) ?? 1) - (topicRank.get(topic(b)) ?? 1) ||
      topicOrder.indexOf(topic(a)) - topicOrder.indexOf(topic(b)) ||
      severity(a) - severity(b),
  );
}
