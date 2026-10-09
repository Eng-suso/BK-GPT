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
| Audio | **Nessuno.** Il racconto passa da testo a schermo e cursore; le chat dell'agente si vedono in streaming |
| Lingua | Italiano principale, inglese seconda versione dallo stesso script |
| Frase di chiusura | **Dalle interviste a un processo che puoi difendere.** |
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

## Il gancio: la settimana del consulente

Il pubblico e' il consulente di processo e il piccolo studio di consulenza. Il
gancio non spiega DeliR: racconta la loro settimana, con le loro parole
(problema nei primi 3 secondi, prodotto subito dopo). Il cliente dice di
conoscere il processo; le interviste mostrano che ognuno ne conosce un pezzo;
venerdi' la mappa va difesa davanti al cliente.

| Giorno | Testo |
| --- | --- |
| Lunedì | Kick-off da Vetrano Industriale. «Il processo acquisti? Lo conosciamo.» |
| Martedì | Tre interviste. Ognuno conosce un pezzo. |
| Mercoledì | Nessuno sa chi sistema gli ordini urgenti. |
| Venerdì | Presenti la mappa al cliente. E devi difenderla. |

La frase del lunedi' e' del cliente-tipo, non delle interviste: e' l'unica
battuta non presa dal golden set, e non e' attribuita a nessuno.

## Storyboard (muto)

Il percorso: interviste → As-Is → review dell'As-Is con DeliR → As-Is
corretto → simulazione e heatmap → verifica sull'event log del cliente →
review del To-Be con DeliR → ipotesi → simulazione To-Be → decisione →
export per il process owner → memoria. Le chat sono in streaming (fasi di
lavoro, poi testo che arriva a pezzi), come dal backend.

| Scena | Cosa si vede | Testo a schermo |
| --- | --- | --- |
| 01-settimana | Le quattro card del gancio | — |
| 02-interviste-a-delir | Chat di processo: il consulente scrive, DeliR legge le 3 interviste e risponde | Carichi le interviste. DeliR le legge con te. |
| 03-fonti | Intervista con le affermazioni e le citazioni verificate | Ogni affermazione, con la sua citazione. |
| 04-passaggio-nascosto | Divergenze: i due "non so" e il "la faccio io" di Francesca | Due non sanno chi sistema l'urgenza. Francesca sì. |
| 05-lacuna | Soglia di autorizzazione: domanda aperta | Quello che nessuno ha detto, DeliR te lo chiede. |
| 06-as-is | BPMN a 6 corsie, evidenze al 100%, citazione sul task urgente | La bozza As-Is. Ogni passaggio ha una fonte. |
| 07-review-as-is | Review mode su "Regolarizza ordine a posteriori": domanda e risposta in streaming | Rivedi l'As-Is con DeliR, attività per attività. |
| 08-as-is-corretto | Proprietà del task, cronologia "As-Is v3 · validato con Laura Conti" | Correggi tu: è la versione che firmi. |
| 09-simula-as-is | Replay con 6 grafici in movimento | Simuli il processo di oggi. |
| 10-heatmap | Attesa per attività, Autorizza spesa in rosso | Si ferma all'autorizzazione: quasi 3 giorni. |
| 11-event-log | Export del gestionale → qualità e KPI → reale contro simulato | Lo verifichi sui dati del cliente: scarto 2%. |
| 12-review-to-be | Review mode su "Autorizza spesa": proposta To-Be in streaming | Chiedi a DeliR come migliorarlo. |
| 13-ipotesi-to-be | Ipotesi con la citazione di chi le ha chieste | Le proposte vengono da chi lavora nel processo. |
| 14-simula-to-be | Stesse richieste, la coda sparisce | Stesse richieste. Processo nuovo. |
| 15-decidi | Confronto KPI e verdetto | −75% di attraversamento, −29% di costo. Simulato. |
| 16-process-owner | Diagramma To-Be separato, "Scarica BPMN", prossimo passo del progetto | Esporti il To-Be per Laura Conti, process owner. |
| 17-memoria | Progetto → cliente → portafoglio | Tutto resta nella memoria di DeliR. / Al prossimo cliente non riparti da zero. |
| 18-chiusura | Marchio | Dalle interviste a un processo che puoi difendere. |

**Tagli** (`storyboard.json` → `cuts`, stesso girato): **90 s** movimentato
(11 scene, testo 2 s) e **2'30"** esteso (17 scene, testo 2,3 s). Le chat
hanno tre velocita' legate ai marker della registrazione: digitazione 3–3,5×,
risposta in streaming 1,2–1,5× (si legge), rilettura 2,5×. Loop hero: review dell'As-Is + replay As-Is.

## Regole del video muto

- Un testo per scena, corto, almeno 2 s a schermo (taglio 90 s) o 2,6 s (esteso).
- Prima il testo, poi l'azione: mai testo sopra una UI che cambia.
- Le chat si registrano da vicino (1280×720 a densita' 1,5): a 1920 il testo si legge.
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
| Simulare | replay As-Is, replay To-Be (processo + 6 KPI in movimento) | i due replay |
| Collo di bottiglia | heatmap dell'attesa | heatmap |
| Decidere | confronto KPI | — |
| Memoria | progetto con fonti, versioni, simulazioni | zoom out |

Generazione: `npm run media:launch` (cattura + montaggio; solo montaggio:
`npm run media:launch:render`). Output in `artifacts/launch-media/` (non
versionato): `screens/` (PNG 3840×2160), `landing/` (MP4 + WebM + poster per
sezione, `hero-loop`), `scenes/`, `video/delir-90s-it.mp4`, `video/delir-150s-it.mp4` (e
`video/delir-presentazione-it.mp4` con tutte le scene per intero).

Dove il Chromium installato non e' quello di Playwright:
`PLAYWRIGHT_CHROMIUM_EXECUTABLE=/percorso/chrome npm run media:launch`.

## Da dove vengono i dati

| Cosa | Fonte |
| --- | --- |
| Event log | altra run Prosimos dell'As-Is (seed 7, 240 casi) esportata come dal gestionale + registrazione fattura; analisi di `backend.eventlog.analysis.analyze` (`scripts/launch_media_eventlog.py`) |
| Interviste, claim, citazioni, evidenze | golden set `tests/golden/esaote_ciclo_passivo` (alla lettera; il modulo dati si ferma se una citazione non si trova) |
| BPMN As-Is | compilatore del prodotto (`data/as-is.compiled.bpmn`), corretto in v3 da `scripts/launch_media_asis.py` |
| KPI, replay, confronto, esperimenti | Prosimos 2.1.0 + funzioni del backend (`scripts/launch_media_simulate.py`), seed fisso |
| Volume (5 richieste/giorno), persone, costi orari, effetto del To-Be | assunzioni del consulente, dichiarate come tali nella provenienza dei parametri |

Risultato della simulazione (360 richieste): attraversamento medio
**2g 21h → 17h 46min (−75%)**, costo per caso **−29%**; collo di bottiglia
As-Is **Autorizza spesa** (il responsabile c'e' due ore a settimana e nessuno
lo sostituisce).

## La correzione dell'As-Is (v3)

Il compilatore produce BPMN valido ma non nello stile che un consulente
presenterebbe: un gateway con due domande e tre uscite, default non dichiarati,
join impliciti su tre elementi, un solo evento di fine per due esiti, "Start" e
"End" generici, corsie in ordine di compilazione. La v3 tiene le stesse
attivita' (stessi id) e corregge questi punti; `analyze_control_flow` la da'
sound senza warning. I gateway di merge restano senza nome, come vuole lo stile
BPMN: le domande stanno sugli split.

## Cosa non scrivere

- Nessun claim di isolamento fra organizzazioni o sicurezza multi-tenant finché
  Track B (`docs/deployment-and-tenancy.md`) non è chiusa.
- Nessuna soglia numerica di autorizzazione.

## Gap di prodotto aperti

| Area | Gap |
| --- | --- |
| Compilatore BPMN | Un gateway per domanda, default dichiarati ed etichettati, merge espliciti, un evento di fine per esito, nomi di inizio/fine, ordine delle corsie, layout ortogonale: oggi li corregge a mano la v3 |
| Creare il To-Be | Le ipotesi To-Be esistono; manca l'azione "Crea To-Be da questo As-Is" (copia collegata del modello) |
| Process owner | Manca l'invio al process owner (e la sua validazione): oggi `owner` è un campo di testo e le decisioni di progetto sono in sola lettura. Il video mostra l'export del To-Be ("Scarica BPMN") e il prossimo passo del progetto, non un invio |
| Review mode | La chat di review non mostra le fasi di lavoro (solo "Sto esaminando il processo…"), quella di processo si' |
| Tela di simulazione | Il layout del video e' scritto nel `localStorage` come lo salva "Modifica canvas": manca un layout "presentazione" predefinito |
| Versione inglese | Mancano i testi EN in storyboard.json e la cattura con l'interfaccia in inglese |
