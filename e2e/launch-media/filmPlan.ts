/**
 * Il film del prodotto: l'incarico intero, dal portafoglio dello studio
 * all'approvazione del cliente, in capitoli. Ogni scena ha la sua targhetta
 * blu, numerata con il capitolo, che dice cosa succede (piano video: una
 * frase per scena, nel video).
 *
 * `take` e' la ripresa da montare: le scene nuove sono in film.spec.ts, le
 * altre riusano i momenti dell'hero (stesso prodotto, stesso caso).
 */
import type { Lang } from "./vetrano";

export type FilmScene = { id: string; take: string; tag: Record<Lang, string> };
export type FilmChapter = { title: Record<Lang, string>; line: Record<Lang, string>; scenes: FilmScene[] };

const scene = (id: string, it: string, en: string, take = `film-{lang}-${id}`): FilmScene => ({ id, take, tag: { it, en } });

export const FILM_INTRO = {
  it: { title: "Settimane per capire come lavora davvero il cliente.", line: "Interviste, procedure, mail: un incarico di processo parte sempre cosi'." },
  en: { title: "Weeks to understand how the client really works.", line: "Interviews, procedures, emails: every process engagement starts like this." },
} as const;

export const FILM_OUTRO = {
  it: { title: "DeliR.", line: "Dalle fonti alla proposta che il cliente approva. delir.it" },
  en: { title: "DeliR.", line: "From the sources to the proposal the client approves. delir.it" },
} as const;

export const FILM: FilmChapter[] = [
  {
    title: { it: "Lo studio", en: "The practice" },
    line: { it: "Clienti, incarichi e processi in un posto solo", en: "Clients, engagements and processes in one place" },
    scenes: [
      scene("01-home", "Tutti i clienti e gli incarichi dello studio", "Every client and engagement in the practice"),
      scene("02-consulente", "Chiedi a DeliR: apre cliente e progetto per te", "Ask DeliR: it opens the client and project for you"),
      scene("03-progetto", "Obiettivo, avanzamento e processi dell'incarico", "The engagement's goal, progress and processes"),
    ],
  },
  {
    title: { it: "Le fonti", en: "The sources" },
    line: { it: "Ogni affermazione con la sua frase esatta", en: "Every statement with its exact sentence" },
    scenes: [
      scene("04-fonti", "Ogni affermazione ha la sua citazione verificata", "Every statement has its verified quote"),
      scene("05-discussione", "Dalle interviste l'As-Is, con le domande aperte", "From the interviews to the As-Is, with open questions"),
    ],
  },
  {
    title: { it: "L'As-Is", en: "The As-Is" },
    line: { it: "Il processo disegnato, con le sue fonti", en: "The process drawn, with its sources" },
    scenes: [
      scene("06-disegno", "Interviste e file del cliente diventano il processo", "Interviews and client files become the process", "hero-{lang}-1-fonti"),
      scene("07-evidenze", "Ogni attività con la frase che la regge", "Every activity with the sentence behind it", "hero-{lang}-2-evidenze"),
      scene("08-da-confermare", "Ciò che nessuna fonte dice resta da confermare", "What no source says stays to be confirmed"),
    ],
  },
  {
    title: { it: "La review", en: "The review" },
    line: { it: "Rivedi ogni attività con DeliR", en: "Review every activity with DeliR" },
    scenes: [
      scene("09-review", "DeliR risponde con le fonti e i dati simulati", "DeliR answers with the sources and simulated data"),
    ],
  },
  {
    title: { it: "La simulazione", en: "The simulation" },
    line: { it: "Dove si ferma il processo, misurato", en: "Where the process stalls, measured" },
    scenes: [
      scene("10-as-is", "Simula l'As-Is: ecco il collo di bottiglia", "Simulate the As-Is: here is the bottleneck", "hero-{lang}-3-simulazione"),
      scene("11-insight", "Cosa provare, con l'effetto stimato", "What to try, with the estimated effect"),
    ],
  },
  {
    title: { it: "Il To-Be", en: "The To-Be" },
    line: { it: "Le proposte nascono da chi lavora nel processo", en: "Proposals come from the people in the process" },
    scenes: [
      scene("12-ipotesi", "Le proposte, con le parole di chi le chiede", "The proposals, in the words of those who ask for them"),
      scene("13-to-be", "Il To-Be: da rosso a verde, −87% di tempo", "The To-Be: from red to green, −87% time", "hero-{lang}-4-tobe"),
    ],
  },
  {
    title: { it: "La consegna", en: "The handover" },
    line: { it: "Al cliente, una proposta che puoi spiegare", en: "A proposal you can explain, to the client" },
    scenes: [
      scene("14-pronto", "DeliR controlla che sia pronto per il cliente", "DeliR checks it's ready for the client"),
      scene("15-invio", "Invia al cliente con un link privato", "Send it to the client with a private link", "hero-{lang}-5-invio"),
      scene("16-cruscotto", "Il cliente legge cosa cambia e perché", "The client reads what changes and why"),
      scene("17-approvato", "Il cliente approva: è la versione di riferimento", "The client approves: it's the reference version"),
    ],
  },
  {
    title: { it: "Tutto resta", en: "Everything stays" },
    line: { it: "Nel portafoglio dello studio, e si ritrova", en: "In the practice's portfolio, easy to find" },
    scenes: [
      scene("18-ritrova", "Modelli e ricerca: ogni incarico si ritrova", "Models and search: every engagement can be found"),
    ],
  },
];

/** Le scene girate per il film (le altre sono riprese dell'hero). */
export const FILM_TAKES = FILM.flatMap((chapter) => chapter.scenes).filter((item) => item.take.startsWith("film-"));
