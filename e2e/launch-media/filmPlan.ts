/**
 * Il prodotto in 5 moduli, uno per tab della sezione "La soluzione, nel tuo
 * lavoro" di delir.it (delir-landing, src/components/Journey.tsx). Ogni
 * modulo e' una clip autonoma con il nome della clip iniziale della sua tab,
 * cosi' il sito la prende senza cambiare codice; il film del prodotto e' la
 * somma dei moduli, con un'apertura e una chiusura.
 *
 * Le targhette (testi approvati da Sohayb il 14 ottobre) dicono cosa fai e
 * cosa ottieni, in seconda persona e senza gergo. Il titolo della tab resta
 * sul sito, nel DOM: il video non lo ripete.
 *
 * Una ripresa puo' portare piu' targhette in sequenza (`at`: secondi
 * dall'inizio della ripresa). `take` con `hero-` riusa i momenti dell'hero.
 */
import type { Lang } from "./vetrano";

export type FilmTag = { at: number; text: Record<Lang, string> };
export type FilmShot = { take: string; tags: FilmTag[] };
export type FilmModule = { id: string; file: string; name: Record<Lang, string>; shots: FilmShot[] };

const tag = (at: number, it: string, en: string): FilmTag => ({ at, text: { it, en } });
const film = (id: string) => `film-{lang}-${id}`;

export const MODULES: FilmModule[] = [
  {
    id: "contesto",
    file: "memoria",
    name: { it: "Contesto", en: "Context" },
    shots: [
      { take: film("01-home"), tags: [tag(0, "Tutti i tuoi clienti in un colpo d'occhio", "All your clients at a glance")] },
      { take: film("02-consulente"), tags: [tag(0, "Scrivi a DeliR: apre cliente e progetto", "Write to DeliR: it opens client and project")] },
      { take: film("18-ritrova"), tags: [tag(0, "Cerchi un nome, ritrovi tutto", "Search a name, find everything")] },
    ],
  },
  {
    id: "evidenze",
    file: "evidenze-sul-processo",
    name: { it: "Evidenze", en: "Evidence" },
    shots: [
      { take: "hero-{lang}-1-fonti", tags: [tag(0, "Carichi interviste e file del cliente", "Upload interviews and client files"), tag(1.6, "DeliR disegna il processo", "DeliR draws the process")] },
      { take: "hero-{lang}-2-evidenze", tags: [tag(0, "Clicchi un'attività: vedi chi l'ha detto", "Click an activity: see who said it")] },
    ],
  },
  {
    id: "lacune",
    file: "lacuna-aperta",
    name: { it: "Lacune", en: "Gaps" },
    shots: [
      { take: film("05-discussione"), tags: [tag(0, "DeliR ti dice dove le versioni non tornano", "DeliR tells you where the accounts don't match")] },
      { take: film("08-da-confermare"), tags: [tag(0, "Ciò che nessuno ha detto non lo inventa", "What nobody said, it doesn't invent")] },
    ],
  },
  {
    id: "scenari",
    file: "confronto",
    name: { it: "Scenari", en: "Scenarios" },
    shots: [
      { take: "hero-{lang}-3-simulazione", tags: [tag(0, "Simuli il processo: ecco dove si blocca", "Simulate the process: here's where it stalls")] },
      { take: film("09-review"), tags: [tag(0, "Chiedi a DeliR perché: risponde con le fonti", "Ask DeliR why: it answers with the sources")] },
      { take: "hero-{lang}-4-tobe", tags: [tag(0, "Con le modifiche: −87% di tempo", "With the changes: −87% time")] },
    ],
  },
  {
    id: "decisioni",
    file: "review-to-be",
    name: { it: "Decisioni", en: "Decisions" },
    shots: [
      { take: film("12-ipotesi"), tags: [tag(0, "Ogni proposta parte dalle parole del cliente", "Every proposal starts from the client's words")] },
      { take: "hero-{lang}-5-invio", tags: [tag(0, "Mandi al cliente un link privato", "Send the client a private link")] },
      { take: film("16-cruscotto"), tags: [tag(0, "Il cliente vede cosa cambia e perché", "The client sees what changes and why")] },
      { take: film("17-approvato"), tags: [tag(0, "Il cliente approva", "The client approves")] },
    ],
  },
];

/** L'ordine del film segue il lavoro: contesto, fonti, lacune, simulazione, decisione. */
export const FILM_ORDER = ["contesto", "evidenze", "lacune", "scenari", "decisioni"] as const;

export const FILM_INTRO = {
  it: { title: "Settimane per capire come lavora davvero il cliente.", line: "Con DeliR parti dalle interviste e arrivi a una proposta che il cliente approva." },
  en: { title: "Weeks to understand how the client really works.", line: "With DeliR you start from the interviews and reach a proposal the client approves." },
} as const;

export const FILM_OUTRO = {
  // L'invito all'azione e' quello del sito (delir-landing, src/lib/publicOffer.ts).
  it: { title: "Dalle interviste alla proposta approvata.", line: "Entra nella lista d'attesa · delir.it" },
  en: { title: "From the interviews to the approved proposal.", line: "Join the waitlist · delir.it" },
} as const;
