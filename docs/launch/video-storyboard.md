# DeliR — video di presentazione e media della landing

Riferimento fisso del video e degli asset della landing. Come lo scenario E2E:
da qui in poi cambia il prodotto, non la storia.

## Decisioni

| Tema | Decisione |
| --- | --- |
| Protagonista | Il consulente (Marco), non DeliR |
| Caso | Golden set `esaote_ciclo_passivo` (3 interviste: Laura Conti, Paolo Marchetti, Francesca Neri) |
| Cliente a schermo | **Vetrano Industriale S.p.A.** (fittizio). Esaote non compare mai negli asset pubblici |
| Process owner | **Laura Conti** |
| Audio | **Nessuno.** Il racconto passa da testo a schermo, camera (zoom/focus) e cursore |
| Lingua | Italiano principale, inglese seconda versione dallo stesso script |
| Frase guida | **Non disegnare il processo. Dimostralo.** |
| Disclaimer fisso | *Azienda e persone fittizie · caso dimostrativo* |

## Perché non c'è una contraddizione

`expected.json` del golden set ha `expected_conflicts: []` e mette "5000 euro"
fra i `forbidden` (la cifra viene dal processo facility, non da questo). La
storia si regge su cio' che le fonti dicono davvero:

1. **Il passaggio nascosto.** Laura e Paolo non sanno chi regolarizza un
   acquisto urgente; Francesca dice che lo fa lei, e che Paolo non lo sa.
2. **La lacuna che DeliR non riempie.** Nessuna fonte dice la soglia di
   autorizzazione: resta una domanda aperta, non un numero inventato.
3. **Il To-Be l'hanno chiesto loro.** Richiesta completa con campi
   obbligatori (Laura, Francesca), autorizzazione visibile (Francesca).

## Storyboard (muto, ~1'57")

| Tempo | Momento | Cosa si vede | Testo a schermo |
| --- | --- | --- | --- |
| 0–10 s | Gancio | Card citazioni: Laura "…non so da chi.", Paolo "…non voglio dirti un nome a caso." | Nessuno conosce il processo intero. |
| 10–20 s | Capire | Fonti → claim → contatori | Fatti, ipotesi, lacune. Separati. |
| 20–27 s | Passaggio nascosto | I due "non so" collegati alla risposta di Francesca | Due non sanno. Una sì. |
| 27–34 s | Lacuna | Soglia di autorizzazione: nessuna fonte, domanda aperta | DeliR non inventa. Te lo chiede. |
| 34–46 s | Validare + tracciare | BPMN a 6 lane, zoom su "Regolarizza ordine" → citazione | Ogni passaggio ha una fonte. |
| 46–54 s | Correggere l'As-Is | Lacuna chiusa, "As-Is v3 · validato" | L'ultima parola è tua. |
| 54–66 s | Simulare l'As-Is | Token nel ciclo di rilavorazione, coda su "Autorizza spesa" | Oggi: più di metà delle richieste torna indietro. |
| 66–74 s | Creare il To-Be | Modifiche con la citazione di chi le ha chieste | Il To-Be l'avevano già chiesto loro. |
| 74–84 s | Simulare il To-Be | Stesse richieste, la coda sparisce | Stesse richieste. Processo nuovo. |
| 84–94 s | Decidere | Confronto KPI e verdetto (numeri dalla simulazione) | Non un'opinione. Una simulazione. |
| 94–102 s | Process owner | Invio a Laura Conti, stato "In validazione" | Pronto per il process owner. |
| 102–113 s | Memoria | Zoom out processo → progetto → cliente → portafoglio | Tutto resta nella memoria di DeliR. / Per ogni cliente. Per ogni progetto. |
| 113–117 s | Chiusura | Logo, URL | Non disegnare il processo. Dimostralo. |

Tagli dallo stesso girato: **loop hero 20 s** (20–34 s + 54–60 s), **social 45 s**.

## Regole del video muto

- Un testo per scena, massimo 7 parole, almeno 2,5 s a schermo.
- Prima il testo, poi l'azione: mai testo sopra una UI che cambia.
- La camera racconta: zoom sull'elemento, il resto si scurisce.
- I testi si generano nel browser durante la cattura (IT/EN dallo stesso script).
- I numeri dei KPI escono dalla simulazione Prosimos, non dalla sceneggiatura.
- Volume e costi orari non sono nelle fonti: a schermo sono "assunzione del consulente".

## Media per la landing

| Sezione | Screenshot | Clip in loop |
| --- | --- | --- |
| Hero | processo validato con pannello evidenze | replay As-Is |
| Capire | fonti e claim | upload → claim |
| Verificare | lacuna aperta, passaggio nascosto | — |
| Ogni passaggio ha una fonte | canvas + citazione | click su task → evidenza |
| Simulare | replay As-Is, replay To-Be | i due replay |
| Decidere | confronto KPI | — |
| Memoria | progetto con fonti, versioni, simulazioni | zoom out |

Generazione: `npm run media:launch` (vedi `e2e/launch-media/`). Output in
`artifacts/launch-media/` (non versionato).

## Cosa non scrivere

- Nessun claim di isolamento fra organizzazioni o sicurezza multi-tenant finché
  Track B (`docs/deployment-and-tenancy.md`) non è chiusa.
- Nessuna soglia numerica di autorizzazione.

## Gap di prodotto aperti

| Scena | Gap |
| --- | --- |
| Creare il To-Be | Manca l'azione "Crea To-Be da questo As-Is" (copia collegata) |
| Process owner | Manca il flusso di invio/validazione: oggi `owner` è un campo di testo |
