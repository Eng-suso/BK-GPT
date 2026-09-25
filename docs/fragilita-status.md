# Fragilità del prodotto — stato dei lavori

Documento vivo. L'analisi che lo ha prodotto sta in
[`fragilita-audit.md`](fragilita-audit.md) e non si tocca: è la fotografia del
24 settembre 2026. Qui c'è cosa è stato chiuso, cosa manca, e qual è il
prossimo passo.

**A chi serve:** a più sessioni agente in parallelo, e a Sohayb per sapere dove
siamo senza rileggere i diff.

**Come si usa.** Chi prende in mano il lavoro legge §② e fa quello. Chi lo posa
aggiorna §① (la riga del difetto che ha chiuso), §② (il prossimo passo, uno
solo) e §⑤ (la riga di log). Un difetto non si dichiara chiuso se i suoi test
non sono verdi: §① distingue *scritto* da *verificato*, ed è la distinzione che
vale.

**Regole di ingaggio** (§③) prima di toccare qualcosa: ci sono difetti che non
si chiudono senza una decisione di Sohayb, e provarci produce lavoro da buttare.

Ultimo aggiornamento: 2026-09-25.
Branch di lavoro: `fix/fragilita-audit`. Ondata 1 (backend) chiusa; ondata 2 (frontend) in corso.

---

## ① Stato

Stati possibili: **da fare** · **in corso** (con branch) · **scritto** (codice
fatto, test non ancora verdi) · **fatto, verificato** · **bloccato** (serve una
decisione, §④).

### Backend

| ID | Difetto | Gravità | Stato |
| --- | --- | --- | --- |
| B1 | Il tenant arriva da un header, non dalla credenziale | Bloccante | **bloccato** — §④.1 |
| B2 | Autenticazione spenta di default, CORS `*`, tutti admin | Bloccante | **fatto, verificato** — `663a670` |
| B3 | Memoria di un consulente solo (`default_consultant_id`, 20 punti) | Bloccante | **bloccato** — §④.2 |
| B4 | Architettura mono-processo non dichiarata né difesa | Alto | **bloccato** — §④.6 |
| B5 | 73 handler su 76 sono `def` sync: threadpool a 40 posti | Alto | da fare |
| B6 | `_TRACE_EVENTS` mai potato: leak di memoria certo | Alto | **fatto, verificato** — `d3c9544`, `7fc5cb5` |
| B7 | La risposta si perde se il client cade a metà stream | Bloccante | **fatto, verificato** — `4004d7e` |
| B8 | Run di simulazione `pending` per sempre dopo un crash | Alto | **fatto, verificato** — `549d421` |
| B9 | `str(exc)` verso il client (3 punti reali, non 20) | Medio | **fatto, verificato** — `3a46612` |
| B10 | Spesa LLM senza tetto | Alto | **bloccato** — §④.3 |
| B11 | La traccia di osservabilità non è legata al tenant | Medio | **fatto, verificato** — `d3c9544` |
| B12 | Liste senza `LIMIT` né paginazione | Medio | da fare |

### UI

| ID | Difetto | Gravità | Stato |
| --- | --- | --- | --- |
| U1 | Nessun ErrorBoundary: un throw è schermo bianco | Bloccante | **fatto, verificato** — `10b84ce` |
| U2 | Zero code splitting: `bpmn-js` e `recharts` nel bundle iniziale | Medio | **fatto, verificato** — `09c3fb0` |
| U3 | La Simulazione mostra `0` al posto di «nessun dato» | Alto | **fatto, verificato** — `7217075` |
| U4 | 110 stringhe italiane scritte nel codice, fuori da i18next | Alto | da fare |
| U5 | Accessibilità verificata con axe su una pagina sola | Alto | **fatto, verificato** — `6a19b57` |
| U6 | L'errore del backend si legge in interfaccia come sta | Medio | **fatto, verificato** — `3a46612`, chiuso da B9 |
| U7 | PWA dichiarata, PWA assente | Medio | **bloccato** — §④.4 |

### UX

| ID | Difetto | Gravità | Stato |
| --- | --- | --- | --- |
| X1 | «Cronologia eliminata» senza conferma né annulla | Alto | **fatto, verificato** — `cda5adf` |
| X2 | Clienti è un elenco che non si apre | Alto | **bloccato** — §④.5 |
| X3 | URL sbagliato, rimando muto a `/projects` | Medio | **fatto, verificato** — `7f01a30` |
| X4 | La ricerca globale cerca il cliente per nome, non per id | Medio | da fare |
| X5 | Nessun tetto alle simulazioni concorrenti | Medio | **fatto, verificato** — `d91ef7f` |

### Verifica

| ID | Difetto | Gravità | Stato |
| --- | --- | --- | --- |
| V1 | La suite `e2e/` non attraversa il backend: tutto mockato | Bloccante | da fare |
| V2 | Visual regression e Lighthouse opt-in, non bloccano il merge | Medio | da fare |

---

## ② Prossimo passo

**Uno solo.** Chi prende il lavoro fa questo, poi riscrive questa sezione.

> **Ondata 3 — la verifica che manca (V1).**
> Un job CI che attraversa davvero il prodotto: Postgres, backend con
> `DELIR_FAKE_LLM=1`, frontend, uno script di seed, e le spec Playwright senza
> `page.route`. Senza, B7, B8, B9 e B11 restano difetti che nessun test vede —
> e le prossime ondate aggiungono codice che nessuno attraversa.
>
> Il piano esiste già nel ramo `chore/e2e-foundations` (seam fake-LLM, contract
> test): manca il job e il seed.
>
> Dopo, in ordine: U4 (110 stringhe fuori da i18next, la chat resta italiana in
> inglese), B12 (paginazione), B5 (handler sync).

**Ondata 2 — frontend — chiusa** il 2026-09-25: U1, U2, U3, U5, X1, X3, X5.
Sette commit, un test per difetto. U4 non era in questa ondata e resta aperto.

**Ondata 1 — backend — chiusa** il 2026-09-24: B2, B6, B7, B8, B9, B11, U6.
Sei commit, un test per difetto. B4 è uscito dall'ondata ed è diventato una
decisione (§④.6): il fix vero è un lock distribuito o un deploy dichiarato
mono-processo, e la scelta appartiene a Track A.

---

## ③ Regole di ingaggio

1. **Un difetto, un commit.** Il messaggio dice cosa smette di succedere, non
   quale file è cambiato. Italiano, a nome di Sohayb Raqaq, nessun trailer di
   co-autore.
2. **Un difetto non è chiuso senza un test che lo riproduce.** Il test va
   scritto prima del fix e deve fallire prima e passare dopo. Se il difetto non
   è riproducibile in test (B4, B5), lo dice §① nella riga.
3. **Non allargare.** L'audit ha 26 righe; non se ne aggiungono altre qui senza
   passare da §⑤. Un difetto nuovo trovato strada facendo va in
   §⑤ se esce da una review di questo lavoro, in [`bugs.md`](bugs.md) se è un
   comportamento sbagliato riproducibile.
4. **Frontend: si usano le skill del routing** in `CLAUDE.md`, le più piccole
   che servono. Per U1/U3: `react-ui-patterns`, `frontend-dev-guidelines`. Per
   U5: `accessibility-compliance-accessibility-audit`, `wcag-audit-patterns`.
   Per U2: `react-best-practices`.
5. **I bloccati non si toccano.** Prima la decisione in §④, poi il codice.
   Scrivere B1 o B3 senza la decisione significa riscriverli dopo.
6. **Chi posa il lavoro aggiorna §①, §② e §⑥ nello stesso commit del fix.** Un
   documento vivo aggiornato in un commit a parte è un documento morto.

---

## ④ Cosa serve da Sohayb

Cinque decisioni. Finché non arrivano, i difetti che dipendono da loro restano
**bloccati** in §①, e questo è corretto: non sono dimenticanze.

1. **B1 — a cosa si lega lo spazio di lavoro.** Oggi è un header e il token sta
   nel browser. Le strade sono due: (a) un token per spazio di lavoro, con la
   mappa token → tenant lato server, che si fa subito e regge un pilota singolo;
   (b) Track B con Supabase Auth, identità per persona, che è la strada vera e
   costa settimane. Se la risposta è (b), B1 e B3 si chiudono insieme e questa
   ondata non esiste.
2. **B3 — quando muore `default_consultant_id`.** È lo stesso bivio di B1: la
   memoria per consulente ha senso solo se esiste il consulente. Vedi
   [`deployment-and-tenancy.md`](deployment-and-tenancy.md), Track B.
3. **B10 — chi paga e quanto.** Il gateway registra la spesa e non la ferma. Il
   tetto è P0.4 in [`llm-spend-status.md`](llm-spend-status.md): serve una chiave
   per ambiente e un limite mensile deciso da te, non dal codice.
4. **U7 — la PWA serve davvero?** Il prodotto si chiama PWA e non ha né manifest
   né service worker. O si smette di chiamarla così, o si decide cosa deve
   funzionare offline. La seconda costa; la prima è una riga di documentazione.
5. **X2 — cos'è la schermata di un cliente.** La rotta esiste nel codice e non è
   montata. Serve sapere cosa ci si legge: progetti, storico, memoria del
   cliente, fatturato. Senza, si costruisce un contenitore vuoto.
6. **B4 — quanti processi gira DeliR.** Non era una decisione in partenza, lo è
   diventata guardando il codice. I lock dei turni di chat (`_THREAD_LOCKS`)
   stanno in memoria di processo, e le simulazioni girano in `BackgroundTasks`:
   con due worker uvicorn, due turni sullo stesso thread partono insieme e il
   checkpoint si corrompe. Le code invece sono già sicure (`FOR UPDATE SKIP
   LOCKED`). Due strade: (a) dichiarare il deploy mono-processo e farlo
   rispettare, semplice ma incompatibile con un rolling deploy senza
   interruzione; (b) un lock distribuito su Postgres per `thread_id`, che rende
   il prodotto scalabile davvero e tiene una connessione aperta per tutta la
   durata del turno. È una scelta di Track A, non di questo branch.

---

### Correzioni all'audit

L'audit è la fotografia del 24 settembre e non si riscrive. Dove si è rivelato
impreciso, la riga giusta sta qui.

- **B9 non erano 20 punti, erano 3.** Gli altri diciassette sono messaggi di
  `ValueError` sollevate apposta, in italiano, per chi le legge. Contarli
  insieme faceva sembrare il difetto quattro volte più grande di com'era.
- **U3 non è «la Simulazione non ha stati».** `ReplayGate` gestisce già
  caricamento, `pending`, `failed` e assenza di artefatto, ed è condiviso fra
  Replay e Cruscotto: l'audit contava le occorrenze file per file e non ha
  visto il componente comune. Resta vero, e resta da fare, il pezzo più
  stretto: `SimulationDashboardPage.tsx:194` fa `?? 0` su ogni KPI, quindi un
  summary parziale si legge come «cycle time 0, costo 0» invece che «non
  disponibile». Gravità scesa da Bloccante ad Alto.

---

## ⑤ Trovato fuori perimetro

La review del branch (CodeRabbit, 2026-09-24) ha guardato anche codice già in
`main`. Quattro rilievi sono veri e **non appartengono a questo lavoro**: non
si toccano qui, ma non vanno persi. Chi apre il prossimo branch su quelle aree
parta da qui.

> **Attenzione al limite.** Il piano CodeRabbit è Free: tre review incluse, poi
> `rate_limit`. La seconda passata ha segnalato tre rilievi minori su
> `trace_recorder.py`, `simulation/storage.py` e su questo documento, e la terza
> — quella che serviva per leggerne il testo — è stata rifiutata. Uno dei tre
> l'ho poi trovato da solo ed è chiuso (`7fc5cb5`); degli altri due resta solo
> il nome del file. Chi ha un posto assegnato li rilegga.

| Dove | Cosa | Perché conta |
| --- | --- | --- |
| `backend/workers/conformance_worker.py:83` | I tentativi non hanno un tetto: una riga che fallisce sempre viene ripresa per sempre | La coda non avanza e il log si riempie. Serve parcheggiare dopo N tentativi e distinguere i guasti non transitori |
| `backend/memory/reranker.py:99` | `OperationNotOpen` finisce nel gestore generico e diventa «il modello ha fallito» | Nasconde un errore di programmazione dentro un fallback che sembra normale |
| `backend/memory/knowledge_graph/entity_resolution.py:362` | Stessa cosa del punto sopra | Stessa cura: rilanciare `OperationNotOpen` prima del gestore largo |
| `backend/api/errors.py:126` | `unreadable_plan` manda `detail=str(exc)` al client | Stessa famiglia di B9. Qui il testo è un messaggio scritto apposta, non un'eccezione qualunque, quindi è meno grave — ma il `detail` non serve a chi legge |

---

## ⑥ Log

Una riga per passo chiuso. Chi la scrive mette data, ID del difetto e come si
verifica.

| Data | ID | Cosa è cambiato | Verifica |
| --- | --- | --- | --- |
| 2026-09-24 | — | Audit end-to-end del prodotto: 26 difetti fra backend, UI, UX e verifica. Aperto questo documento e il branch `fix/fragilita-audit`. | [`fragilita-audit.md`](fragilita-audit.md) |
| 2026-09-24 | B6, B11 | Le tracce hanno un tetto (200 tracce, 1000 eventi) e ricordano da quale spazio di lavoro vengono. Una traccia altrui risponde 404 come una che non esiste. | `tests/test_observability.py`, 15 verdi |
| 2026-09-24 | B8 | Una simulazione `pending` oltre il tempo massimo di Prosimos viene chiusa come fallita: il frontend smette di pollare e lo scenario si può rilanciare. | `tests/test_simulation.py::test_a_simulation_killed_mid_run_stops_being_in_flight`, rosso senza il fix |
| 2026-09-24 | B7 | Il salvataggio del turno è passato in un `finally`: una scheda chiusa o uno Stop lasciano in archivio quello che l'agente aveva scritto, marcato come troncato. Il generatore è uscito dalla closure (`chat_turn_events`) per poterlo chiudere in un test. | `tests/test_fake_llm.py::test_a_turn_that_never_ends_still_leaves_what_the_agent_wrote` |
| 2026-09-24 | B9, U6 | Le tre rotte di chat non mandano più `str(exc)`: l'eccezione va nei log con thread e trace, in interfaccia arriva una frase per il consulente, e un timeout (503) si distingue da un guasto (502). **Correzione all'audit:** i punti veri erano 3, non 20 — gli altri 17 sono messaggi di `ValueError` scritti apposta per chi legge. | `tests/test_chat_error_surface.py`, 3 verdi |
| 2026-09-24 | B2 | `DELIR_ENVIRONMENT`: dichiarato `staging` o `prod` senza autenticazione, l'app si rifiuta di partire. In `dev` parte e dice cosa è aperto. | `tests/test_startup_guard.py`, 4 verdi |
| 2026-09-24 | B4 | Uscito dall'ondata 1: non è un fix, è una decisione di deploy. Spostato in §④.6 con le due strade e il loro costo. | — |
| 2026-09-24 | B2, B8 | I due rilievi della review sul mio codice: la lista degli ambienti dice dove partire scoperti è lecito (non dove è vietato), quindi un `DELIR_ENVIRONMENT` scritto male non parte; e un risultato Prosimos che arriva per una simulazione non più `pending` viene scartato invece di riportarla in vita. | `tests/test_startup_guard.py`, `tests/test_simulation.py`, 40 verdi sulle suite toccate |
| 2026-09-25 | B6 | Rilettura del fix stesso: `_remember` serviva sia ad aprire una traccia sia a scriverci, quindi un evento in ritardo resuscitava una traccia sfrattata — senza spazio di lavoro, quindi illeggibile, e occupando un posto. Aprire e scrivere ora sono due cose diverse. | `tests/test_observability.py::test_an_evicted_trace_does_not_come_back_from_the_dead` |
| 2026-09-25 | U1 | Due ErrorBoundary: uno dentro la shell intorno all'`Outlet` (la navigazione sopravvive a una schermata rotta, e cambiare rotta ripulisce l'errore), uno sopra il router. | `ErrorBoundary.test.tsx`, 4 verdi |
| 2026-09-25 | U3 | `formatOrMissing`: un KPI che manca si legge come trattino, uno zero vero resta zero. Toccati Cruscotto e Approfondimenti. | `simulationResults.missing.test.ts`, 4 verdi |
| 2026-09-25 | X1 | `ConfirmDialog` prima di eliminare una conversazione o svuotare la cronologia; il bottone si spegne mentre l'operazione gira. | `ConfirmDialog.test.tsx`, 4 verdi |
| 2026-09-25 | X3 | Una schermata che dice quale indirizzo non esiste, al posto del rimando muto: il tasto indietro torna dove si era. | `NotFoundPage.test.tsx`, 2 verdi |
| 2026-09-25 | U2 | Rotte pigre: pacchetto d'ingresso da 3.218 kB (898 gzip) a 363 kB (113). Le due schermate d'ingresso si precaricano da sole; canvas e Simulazione no, di proposito. | build + 235 unit + 17 e2e in seriale |
| 2026-09-25 | U5 | Axe su nove superfici invece di una, dialogo compreso: zero barriere gravi. Canvas e Simulazione restano scoperti finché non c'è V1. | `e2e/accessibility.spec.ts`, 9 verdi |
| 2026-09-25 | X5 | Tetto alle simulazioni in volo (quattro, sotto i sei worker di Prosimos): oltre, 429 immediato invece di quindici minuti di rotella. | `test_simulation.py`, 13 verdi |
