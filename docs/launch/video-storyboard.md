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
| Frase di chiusura | **Dalle interviste alla decisione del cliente. Con i numeri.** |
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

## Il copy: il dolore del consulente, poi il risultato

Il pubblico e' il consulente di processo e il piccolo studio. Niente slogan:
il gancio dice i quattro problemi che riconosce subito, la promessa dice cosa
porta al cliente, ogni scena risponde a un problema, la card dei risultati
chiude il cerchio con i numeri del caso.

| # | Gancio (un problema per volta) |
| --- | --- |
| 1 | Tre interviste. Tre versioni diverse dello stesso processo. |
| 2 | Giorni a ricostruirlo dagli appunti. |
| 3 | Poi il cliente chiede: «Questo chi l'ha detto?» |
| 4 | E subito dopo: «Quanto ci fa risparmiare?» E tu rispondi a sensazione. |

**Promessa** — Con DeliR, dal cliente arrivi con: un As-Is con la fonte di ogni passaggio, il collo di bottiglia misurato, non intuito, un To-Be con il risparmio già simulato.

**Risultato** — Il risultato per Vetrano Industriale: 38 affermazioni, ognuna con la sua citazione · 2g 22h di attesa sull'autorizzazione, misurata · −75% tempo di attraversamento nel To‑Be · −29% costo per pratica nel To‑Be. Valori simulati · modello As-Is verificato sul log del cliente (scarto 2%).

**Chiusura** — Dalle interviste alla decisione del cliente. Con i numeri.

La domanda «Quanto ci fa risparmiare?» del gancio torna nella scena della
decisione, con la risposta simulata. Le domande del cliente non sono citazioni
delle interviste e non sono attribuite a nessuno.

## Storyboard (muto)

Il percorso: interviste → As-Is → review dell'As-Is con DeliR → As-Is
corretto → simulazione e heatmap → verifica sull'event log del cliente →
review del To-Be con DeliR → ipotesi → simulazione To-Be → decisione →
export per il process owner → memoria. Le chat sono in streaming (fasi di
lavoro, poi testo che arriva a pezzi), come dal backend.

| Scena | Testo a schermo |
| --- | --- |
| 01-gancio | card |
| 01b-promessa | Con DeliR, dal cliente arrivi con: |
| 02-interviste-a-delir | Carichi le interviste. DeliR estrae chi fa cosa. |
| 03-fonti | «Chi l'ha detto?» Ecco la frase esatta. |
| 04-passaggio-nascosto | Le versioni che non tornano escono prima del workshop. |
| 05-lacuna | Quello che nessuno ha detto diventa una domanda per il cliente. |
| 06-as-is | La bozza As-Is arriva già collegata alle fonti. |
| 07-review-as-is | Rivedi ogni attività con DeliR, prima di mostrarla. |
| 08-as-is-corretto | Ogni correzione resta tracciata, versione per versione. |
| 09-simula-as-is | Simuli il processo di oggi, prima di cambiarlo. |
| 10-heatmap | Il collo di bottiglia, misurato: quasi 3 giorni di attesa. |
| 11-event-log | Controlli la simulazione sul log del cliente: scarto 2%. |
| 12-review-to-be | Chiedi a DeliR dove intervenire. Risponde con le fonti. |
| 13-ipotesi-to-be | Il To-Be parte da quello che chiede chi lavora nel processo. |
| 14-simula-to-be | Stesse richieste. Processo nuovo. |
| 15-decidi | «Quanto ci fa risparmiare?» −75% di tempo, −29% di costo. Simulato. |
| 16-process-owner | Il To-Be va al process owner in BPMN, pronto da validare. |
| 17-memoria | Fonti, versioni e simulazioni restano nel progetto. / Il prossimo cliente non parte da zero. |
| 17b-risultato | Il risultato per Vetrano Industriale |
| 18-chiusura | Dalle interviste alla decisione del cliente. Con i numeri. |

**Tagli** (`storyboard.json` → `cuts`, stesso girato): **~90 s** movimentato
(12 scene con le card, testo 2,3 s) e **2'30"** esteso (19 scene, testo 2,3 s). Le chat
hanno tre velocita' legate ai marker della registrazione: digitazione 3–3,5×,
risposta in streaming 1,2–1,5× (si legge), rilettura 2,5×. Loop hero: review dell'As-Is + replay As-Is.

## Regia

I tagli li monta `scripts/launch_media_edit.py`, fotogramma per fotogramma:

- **camera**: in cattura ogni scena registra dove guardare (`rec.focus`,
  `rec.wide`); il montaggio fa zoom e panoramiche con easing in-out (0,9 s) su
  quel rettangolo e torna al campo largo;
- **transizioni**: dissolvenza incrociata di 0,45 s fra le scene, apertura e
  chiusura dal bianco;
- **testi**: entrano dal basso con dissolvenza, durante l'attesa della scena;
- **percorso del consulente**: in alto, le sei tappe (Interviste, As-Is,
  Simulazione, Event log, To-Be, Process owner), quella in corso accesa e le
  precedenti spuntate; il disclaimer in basso a destra.

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
