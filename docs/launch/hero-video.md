# DeliR — video hero della landing

Loop muto di **~12,5 s** nell'hero della landing, accanto a headline e
subheadline. Tre momenti lunghi e leggibili, **niente frasi a schermo**: il
prodotto si capisce guardandolo. Il processo e' sempre **intero**.

Generazione: `npm run media:hero` (cattura + montaggio); uscita in
`landing/media/` (WebM, MP4, poster).

## Il processo dell'hero

Un processo piccolo, apposta: si legge in un colpo d'occhio.
`scripts/launch_media_hero_process.py` lo disegna e lo simula con Prosimos
(stessa pipeline del prodotto).

- Pool "Purchase request", 3 corsie (Requester, Purchasing, Manager).
- 5 attivita', una decisione ("Request complete?") e il suo giro di
  rilavorazione.
- **As-Is**: il 50% delle richieste torna indietro, il manager autorizza due
  volte a settimana. Ciclo medio **2,26 giorni**, collo di bottiglia "Approve
  spend".
- **To-Be**: la richiesta nasce completa (15% di rilavorazione), un delegato
  autorizza in giornata. Ciclo medio **0,12 giorni**.

## Storyboard

| Tempo | Inquadratura | Cosa si vede |
| --- | --- | --- |
| 0–4,6 s | Editor, canvas | Quattro documenti (PDF, trascrizione, Excel, verbale) volano al centro e spariscono. Il processo si compone da sinistra a destra: corsie, poi task e frecce. |
| 4,2–8,8 s | Replay della simulazione As-Is | Processo intero sopra, **4 grafici KPI** sotto. I casi si accumulano su "Approve spend" mentre i grafici crescono. Etichetta "As-Is". |
| 8,4–12,6 s | Schermo diviso: As-Is sopra, To-Be sotto | Stesso flusso di richieste. Sopra la coda resta, sotto scorre. Accanto a ciascun processo ci sono gli stessi 4 grafici. |

Transizioni: dissolvenza incrociata di 0,4 s e camera con easing. Gli ultimi
0,5 s sfumano nel fotogramma iniziale, cosi' il loop non ha stacco.

## I KPI (grafici, non numeri)

Sono i widget della tela di simulazione del prodotto: quelli che il consulente
aggiunge e guarda durante il replay. Il layout e' salvato come lo salverebbe
lui (`heroSimulationLayout` / `heroSimulationLayoutSolo` in
`e2e/launch-media/heroData.ts`).

| Widget | Tipo | Perche' |
| --- | --- | --- |
| Average cycle time | linea | quanto ci mette una richiesta |
| Queued cases | area | dove si accumula il lavoro |
| Throughput | linea | quanto esce dal processo |
| Accrued cost | area | quanto costa il processo |

La disposizione cambia con l'inquadratura:

- nella ripresa singola i grafici stanno **sotto** il processo, e la tela e'
  circa 16:9;
- nello schermo diviso stanno **a destra**, e ogni fascia e' circa 3,5:1.

## Consegna web

- WebM VP9 (principale) + MP4 H.264 (Safari/fallback), 1600×900, senza audio.
- Poster WebP + JPG a 10,8 s (schermo diviso: As-Is bloccato, To-Be che
  scorre).
- `autoplay muted loop playsinline`, `preload="metadata"` + poster in
  preload.
- `prefers-reduced-motion`: niente autoplay, resta il poster.
- Fuori schermo il video si mette in pausa (IntersectionObserver).

| File | Peso |
| --- | --- |
| `landing/media/delir-hero.webm` | ~720 KB |
| `landing/media/delir-hero.mp4` | ~690 KB |
| `landing/media/delir-hero.webp` / `.jpg` (poster) | ~48 / ~111 KB |

`e2e/launch-media/landing.spec.ts` verifica:

- autoplay e loop senza pause;
- che riduci movimento lasci il poster;
- l'assenza di scorrimento orizzontale a 390 px.

## Revisione critica (conversione)

- **Forte**: in 12 s si vede l'intera promessa: dai documenti al processo, il
  collo di bottiglia e il To-Be che lo risolve. Non serve leggere.
- **Forte**: UI vera del prodotto, simulazioni Prosimos vere, disclaimer "Demo
  data · simulated example".
- **Debole**: a 390 px le etichette dei task non si leggono, restano forme e
  grafici. Il prossimo passo per il mobile e' una variante verticale (As-Is e
  To-Be impilati).
- **Da decidere**: accanto alla headline il video e' largo circa 750 px. Se la
  headline si accorcia, metterlo sotto a tutta larghezza rende piu' leggibili i
  grafici.

## Revisione dei fotogrammi (ottobre 2026)

Fotogrammi estratti da `landing/media/delir-hero.mp4` (12,6 s).

| t | Problema | Gravita' | Correzione |
| --- | --- | --- | --- |
| 10,8 s (poster) | As-Is: "15 queued" su "Issue purchase order", "4 queued" su "Approve spend". Il collo di bottiglia che si vede non e' quello raccontato | Alta: e' il fotogramma che vedono tutti prima del play e chi ha riduci movimento | Spostare il poster a un istante in cui la coda massima e' su "Approve spend", oppure fissare il seed/istante del replay |
| ~8 s | Una pillola "Navigation" del canvas entra in basso a sinistra | Media: UI di servizio dentro il prodotto mostrato | Nasconderla durante la cattura in `hero.spec.ts` |
| ~3,5 s | Lo zoom taglia la toolbar ("…ents 12") e il logo BPMN.io a destra | Media: sembra un errore di inquadratura | Allargare il rettangolo `rec.focus` o tenere fuori la toolbar |
| tutta | Il link "See how it works" punta a `#product`, che non esiste | Media: la seconda CTA dell'hero non porta da nessuna parte | Aggiungere la sezione prodotto con le clip della tabella "Media per la landing" |
