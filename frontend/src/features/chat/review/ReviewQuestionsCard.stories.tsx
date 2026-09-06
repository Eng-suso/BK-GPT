import type { Meta, StoryObj } from "@storybook/react";

import { ReviewQuestionsCard } from "./ReviewQuestionsCard";
import "../chat.css";

const meta: Meta<typeof ReviewQuestionsCard> = {
  title: "Chat/ReviewQuestionsCard",
  component: ReviewQuestionsCard,
  parameters: { layout: "padded" },
  args: {
    isAnswering: false,
    onAnswer: async () => {},
  },
};
export default meta;
type Story = StoryObj<typeof ReviewQuestionsCard>;

export const WithAlternatives: Story = {
  args: {
    questions: [
      {
        question_id: "chi-approva-oltre-10k",
        question: "Chi approva un ordine sopra i 10.000 euro?",
        severity: "blocking",
        affects: "decision",
        options: [
          {
            label: "Direzione amministrativa",
            implication: "Aggiunge un passaggio di approvazione dopo la verifica del credito",
          },
          {
            label: "Il responsabile commerciale",
            implication: "L'approvazione resta dentro Sales, senza un nuovo ruolo",
          },
          {
            label: "Nessuno: è automatico",
            implication: "Il punto di decisione sparisce dal disegno",
          },
        ],
        answer: null,
      },
    ],
  },
};

export const SeveralQuestions: Story = {
  args: {
    questions: [
      {
        question_id: "cosa-succede-se-il-credito-non-passa",
        question: "Cosa succede se la verifica del credito non passa?",
        severity: "non_blocking",
        options: [
          { label: "L'ordine viene rifiutato", implication: "Percorso alternativo che chiude il processo" },
          { label: "Si chiede un pagamento anticipato", implication: "Percorso alternativo che rientra nel flusso" },
        ],
        answer: null,
      },
      {
        question_id: "chi-approva-oltre-10k",
        question: "Chi approva un ordine sopra i 10.000 euro?",
        severity: "blocking",
        options: [
          { label: "Direzione amministrativa", implication: "Aggiunge un passaggio di approvazione" },
          { label: "Il responsabile commerciale", implication: "L'approvazione resta dentro Sales" },
        ],
        answer: null,
      },
    ],
  },
};

/** Una domanda davvero aperta: elencare alternative sarebbe indovinare. */
export const WithoutAlternatives: Story = {
  args: {
    questions: [
      {
        question_id: "quali-eccezioni-ricorrenti",
        question: "Quali eccezioni ricorrenti gestisce oggi il team, fuori dal flusso standard?",
        severity: "non_blocking",
        options: [],
        answer: null,
      },
    ],
  },
};
