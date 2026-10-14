/**
 * La chat di DeliR nel film, come in produzione: fasi di lavoro, poi la
 * risposta in markdown, a pezzi, alla velocita' del prodotto.
 *
 * Lo streaming gira dentro la pagina (`installChatStream`): un `fetch` che
 * risponde a `.../messages/stream` con un flusso NDJSON i cui pezzi partono con
 * `setTimeout`. Durante la ripresa a tempo virtuale l'orologio della pagina li
 * scandisce, quindi a video il ritmo e' quello reale (un server esterno
 * arriverebbe a tempo di parete, troppo veloce).
 *
 * I copioni sono quelli di docs/launch/demo-chat-scripts.md; ogni testo fra
 * « » e' una citazione alla lettera delle interviste (in inglese da
 * data/en/quotes.json).
 */
import type { Page } from "@playwright/test";

import type { Lang } from "./vetrano";

export type ChatPhase = { id: string; label: string; icon: string; detail?: string; ms: number };
export type ChatScript = { phases: ChatPhase[]; answer: string };
/** Il tipo di conversazione: la scelta del copione dipende da dove si scrive. */
export type ChatKind = "consultant" | "process" | "review";

const PHASES = {
  it: {
    understanding: "Leggo la richiesta",
    readingWorkspace: "Rileggo i dati del workspace",
    readingSources: "Leggo le fonti raccolte",
    extracting: "Estraggo fatti e punti aperti",
    comparing: "Confronto con le evidenze esistenti",
    modeling: "Costruisco il modello di processo",
    recording: "Aggiorno il registro del progetto",
    drafting: "Preparo la risposta",
  },
  en: {
    understanding: "Reading the request",
    readingWorkspace: "Re-reading the workspace data",
    readingSources: "Reading the collected sources",
    extracting: "Extracting facts and open points",
    comparing: "Comparing with existing evidence",
    modeling: "Building the process model",
    recording: "Updating the project log",
    drafting: "Drafting the answer",
  },
} as const;

/** Cosa scrive il consulente, scena per scena. */
export const PROMPTS = {
  it: {
    consultant: "Nuovo cliente: Vetrano Industriale, acquisti indiretti. Referente Laura Conti.",
    process: "Ricostruisci l'As-Is dalle tre interviste, senza inventare.",
    review: "Perché le richieste si fermano qui?",
  },
  en: {
    consultant: "New client: Vetrano Industriale, indirect purchasing. Contact Laura Conti.",
    process: "Rebuild the As-Is from the three interviews, without inventing.",
    review: "Why do requests get stuck here?",
  },
} as const;

export function chatScripts(lang: Lang): Record<ChatKind, ChatScript> {
  const p = PHASES[lang];
  const it = lang === "it";
  return {
    consultant: {
      phases: [
        { id: "understanding", label: p.understanding, icon: "brain", ms: 700 },
        { id: "reading_workspace", label: p.readingWorkspace, icon: "folder", ms: 1000 },
        { id: "recording", label: p.recording, icon: "edit", detail: it ? "Cliente e progetto" : "Client and project", ms: 1100 },
        { id: "drafting", label: p.drafting, icon: "pen", ms: 500 },
      ],
      answer: it
        ? [
            "Ho aperto il cliente **Vetrano Industriale S.p.A.** e il progetto **Acquisti indiretti**, con Laura Conti come referente.",
            "",
            "Per partire mi servono le fonti: interviste, procedure o mail di chi lavora nel processo. Quando le carichi, estraggo chi fa cosa e ti segnalo dove le versioni non tornano.",
          ].join("\n")
        : [
            "I've opened the client **Vetrano Industriale S.p.A.** and the project **Indirect purchasing**, with Laura Conti as the contact.",
            "",
            "To get started I need the sources: interviews, procedures or emails from the people who work in the process. Once you upload them, I'll extract who does what and flag where the accounts don't match.",
          ].join("\n"),
    },
    process: {
      phases: [
        { id: "understanding", label: p.understanding, icon: "brain", ms: 700 },
        { id: "reading_sources", label: p.readingSources, icon: "document", detail: "Laura Conti, Paolo Marchetti, Francesca Neri", ms: 1500 },
        { id: "extracting", label: p.extracting, icon: "extract", detail: it ? "38 affermazioni con citazione" : "38 statements with a quote", ms: 1300 },
        { id: "modeling", label: p.modeling, icon: "build", ms: 1100 },
        { id: "drafting", label: p.drafting, icon: "pen", ms: 500 },
      ],
      answer: it
        ? [
            "Ho letto le tre interviste ed estratto **38 affermazioni**, ognuna con la sua frase.",
            "",
            "**Il processo**",
            "- La richiesta nasce nel reparto e arriva ad Acquisti per mail: Paolo, «Mail. Sempre mail, a Laura.»",
            "- Acquisti verifica se e' lavorabile e, se manca qualcosa, la rimanda indietro: Francesca, «Leggo e verifico se e' lavorabile.»",
            "- Non tutte le richieste passano dal responsabile: Francesca, «Sopra una certa cifra devo chiedere una autorizzazione al mio responsabile»",
            "",
            "**Da chiarire prima del workshop**",
            "- **Divergenza:** chi regolarizza un acquisto urgente. Laura: «So che poi la parte di carta viene messa a posto dopo, ma non so da chi.» Francesca: «La parte di ordine si', la faccio io.»",
            "- **Lacuna:** nessuna fonte dichiara la soglia di autorizzazione. Non la metto nel modello e te la chiedo.",
          ].join("\n")
        : [
            "I read the three interviews and extracted **38 statements**, each with its own sentence.",
            "",
            "**The process**",
            "- The request starts in the department and reaches Purchasing by email: Paolo, «Email. Always email, to Laura.»",
            "- Purchasing checks whether it's workable and, if something is missing, sends it back: Francesca, «I read it and check whether it's workable.»",
            "- Not every request goes through the manager: Francesca, «Above a certain amount I have to ask my manager for authorization»",
            "",
            "**To clarify before the workshop**",
            "- **Divergence:** who regularizes an urgent purchase. Laura: «I know the paperwork gets sorted out afterwards, but I don't know by whom.» Francesca: «The order part, yes, I do that.»",
            "- **Gap:** no source states the authorization threshold. I'm not putting it in the model, and I'm asking you.",
          ].join("\n"),
    },
    review: {
      phases: [
        { id: "understanding", label: p.understanding, icon: "brain", ms: 600 },
        { id: "reading_sources", label: p.readingSources, icon: "document", detail: it ? "Intervista Francesca Neri" : "Interview Francesca Neri", ms: 1300 },
        { id: "comparing", label: p.comparing, icon: "compare", detail: it ? "Simulazione As-Is" : "As-Is simulation", ms: 1100 },
        { id: "drafting", label: p.drafting, icon: "pen", ms: 500 },
      ],
      answer: it
        ? [
            "**Non e' la valutazione: e' l'attesa.** E riguarda solo le richieste sopra soglia.",
            "",
            "Francesca: «Se e' fuori, possono essere giorni.» e «Non c'e' un sostituto formale»",
            "",
            "Nella simulazione As-Is una richiesta su tre passa dal responsabile e li' aspetta in media **3g 2h**.",
            "",
            "*Valori simulati: la quota sopra soglia e la presenza del responsabile sono assunzioni dello scenario.*",
          ].join("\n")
        : [
            "**It isn't the evaluation: it's the wait.** And it only affects requests above the threshold.",
            "",
            "Francesca: «If he's out, it can be days.» and «There's no formal deputy»",
            "",
            "In the As-Is simulation one request in three goes to the manager and waits there **3d 2h** on average.",
            "",
            "*Simulated values: the share above the threshold and the manager's availability are scenario assumptions.*",
          ].join("\n"),
    },
  };
}

/**
 * Il `fetch` della pagina risponde allo streaming con il copione giusto. Il
 * tipo di conversazione e' nel `thread_id` creato dal mock (`film-<tipo>-n`);
 * a flusso concluso il turno si registra nel mock, cosi' la sessione riletta
 * dal prodotto contiene domanda e risposta.
 */
export async function installChatStream(page: Page, lang: Lang): Promise<void> {
  await page.addInitScript((scripts: Record<ChatKind, ChatScript>) => {
    const PIECE_MS = 38;
    const original = window.fetch.bind(window);
    const pieces = (text: string) => {
      // 1-3 parole per pezzo; un grassetto arriva intero.
      const words = text.split(/(\*\*[^*]+\*\*\S*\s*)|(?<=\s)/).filter(Boolean);
      const out: string[] = [];
      for (let i = 0; i < words.length; ) {
        const size = 1 + ((i * 7) % 3);
        out.push(words.slice(i, i + size).join(""));
        i += size;
      }
      return out;
    };
    window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      const match = url.match(/\/consultant-chat\/sessions\/(film-(consultant|process|review)[^/]*)\/messages\/stream$/);
      if (!match) return original(input, init);
      const [, thread, kind] = match;
      const script = scripts[kind as ChatKind];
      const message = String((JSON.parse(String(init?.body ?? "{}")) as { message?: string }).message ?? "");
      const encoder = new TextEncoder();
      const stream = new ReadableStream<Uint8Array>({
        start(controller) {
          const send = (event: unknown) => controller.enqueue(encoder.encode(`${JSON.stringify(event)}\n`));
          let at = 0;
          const later = (ms: number, fn: () => void) => { at += ms; setTimeout(fn, at); };
          script.phases.forEach((phase, index) => later(index ? script.phases[index - 1].ms : 250, () => send({
            type: "activity", message: phase.label,
            payload: { activity_id: `phase-${index + 1}-${phase.id}`, phase: phase.id, label: phase.label, detail: phase.detail ?? "", icon: phase.icon, elapsed_ms: at, source: "phase" },
          })));
          at += script.phases.at(-1)?.ms ?? 0;
          for (const piece of pieces(script.answer)) {
            later(/[.:;]\s*$/.test(piece) ? PIECE_MS * 4 : /\n/.test(piece) ? PIECE_MS * 3 : PIECE_MS, () => send({ type: "delta", content: piece }));
          }
          later(PIECE_MS, () => {
            send({ type: "done", message: script.answer });
            controller.close();
            void original(url.replace(/\/messages\/stream$/, "/messages/__record"), {
              method: "POST", headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ thread, message, answer: script.answer }),
            });
          });
        },
      });
      return Promise.resolve(new Response(stream, { status: 200, headers: { "Content-Type": "application/x-ndjson" } }));
    };
  }, chatScripts(lang));
}
