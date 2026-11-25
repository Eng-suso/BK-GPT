# Dove siamo adesso

Aggiornato: 2026-11-25, dopo VAL-01 (PR #189), PROTO-01 (PR #190), ENG-01 (PR #191), RAD-00
(PR #192) e la correzione di `DELIR_AUTH_PROVIDER`.

## Punti attivi

Nessuno in corso: ENG-01 è fatto (PR #191). Liberi, con dipendenze chiuse: **G3b** (P0,
percorso critico), **LIC-01** (P0), **RAD-01** → **PROTO-02** (radar), **ANA-01**. Poi
B3.1-B3.3 e B3; ENG-02 dopo LIC-01. Nessun candidato (AT-KDE, POWL, ProSiT,
AgentSimulator) si implementa prima di G3b. I due prompt qui sotto avviano G3b e RAD-01.

## Prompt per i prossimi agenti

Ognuno in una sessione nuova sul repository `eng-suso/bk-gpt`, dal `main` aggiornato.

### Agente 1 — G3b benchmark dei motori scientifici

```text
Lavori sul Verified Process Twin di DeliR, punto G3b di docs/vpt/PLAN.md (P0, percorso
critico). Segui docs/vpt/WORKFLOW.md e CLAUDE.md alla lettera: leggi HANDOFF.md, PLAN.md,
PROTOCOL.md e le ultime tre voci di LOG.md; controlla i branch aperti rispetto a main; metti
G3b "in corso" e lavora sul branch spike/sim-g3b-ablation.

Obiettivo: sui log di sviluppo del protocollo (development_logs(), holdout esclusi) misura
"B = A", SIMOD, SIMOD con ritardi estranei, ProSiT, AgentSimulator, SIMOD con arrivi AT-KDE e
l'ablazione per componente, con le metriche di B2 e IC 95% più tempo di discovery, tempo di
simulazione e picco di memoria. Ogni punto d'ingresso che sceglie qualcosa gira dentro
protocol.selection_phase(); la scelta si fa sulla validazione (train_validation). Prima di
misurare scrivi in LOG.md le schede di go/no-go (§7 di PROTOCOL.md) e rispetta il budget del §6.
Il codice esterno (AT-KDE, ProSiT, AgentSimulator, Kronos) è già nel manifest, collezione
radar: `uv run python scripts/fetch_datasets.py fetch at-kde prosit agentsimulator simod`;
resta nell'ambiente di ricerca, mai importato dal prodotto. Non aprire gli holdout: si aprono
una volta sola con final_evaluation(<impronta>) a selezione congelata, e solo se Sohayb lo
conferma. Stack reale: scripts/vpt_stack.sh start.

Chiusura: risultati in tests/simulation/benchmark/g3b/ con il comando per rifarli, decisione
per componente in LOG.md, HANDOFF.md aggiornato dopo ogni misura. Code review, simplify, CI
verde, merge su main, commit piccoli a nome di Sohayb Raqaq senza trailer Co-Authored-By.
Non abbassare nessuna meta.
```

### Agente 2 — RAD-01 inventario e deduplica, poi PROTO-02

```text
Lavori sul Verified Process Twin di DeliR, punti RAD-01 e poi PROTO-02 di docs/vpt/PLAN.md
(sezione R, Research Radar). Segui docs/vpt/WORKFLOW.md e CLAUDE.md alla lettera: leggi
HANDOFF.md, PLAN.md, RESEARCH_RADAR.md, PROTOCOL.md e le ultime tre voci di LOG.md; controlla
i branch aperti rispetto a main; lavora sul branch chore/radar-inventory.

RAD-01: scarica il radar (`uv run python scripts/fetch_datasets.py fetch --collection radar`,
~2,9 GB, ~24 GB estratti; bpic-ocel2 da solo 18 GB, scaricalo per ultimo o per id). Scrivi
uno script ripetibile che per ogni log del radar riporti casi, eventi, attività, periodo,
risorse, presenza di inizio e fine, osservabilità, e confronti ogni file per SHA-256 e per
nome con i log di sviluppo e con il lucchetto degli holdout
(tests/simulation/benchmark/protocol/holdout.lock.json). Sovrapposizioni note da verificare:
BPIC 2012/2017 dentro ProCause, BPIC 2012 W e 2013 nella copia di Helpdesk, i log di Camargo
nei pacchetti di AgentSimulator e del BPS Quality Framework; Sepsis e Hospital Billing non
devono venire dall'ospedale di BPIC 2011 (holdout). L'audit hook del protocollo resta attivo:
nessun holdout si apre, un file che coincide si marca senza leggerne gli eventi. Report in
tests/simulation/benchmark/radar/inventory.md.

PROTO-02: in PROTOCOL.md dichiara per ogni log del radar sviluppo, nuovo holdout o escluso,
con il motivo; congela per hash un secondo set di holdout indipendenti prima di usarlo;
aggiungi i confronti appaiati accanto agli IC non sovrapposti e le metriche complete di CF-01
(ampiezza, errore puntuale, direzione), senza modificare il benchmark congelato; estendi
test_protocol.py. Le mete marcate proposta vanno confermate da Sohayb prima di chiudere.

Chiusura: HANDOFF.md aggiornato dopo ogni misura, voce in LOG.md, code review, simplify, CI
verde, merge su main, commit piccoli a nome di Sohayb Raqaq senza trailer Co-Authored-By.
```

## RAD-01 → PROTO-02 (in corso dal 2026-11-25)

- Branch `claude/vpt-radar-inventory-j14bbw` (al posto di `chore/radar-inventory`: è il
  branch assegnato alla sessione cloud), allineato a `main` (`687f4e1`).
- Stato: script d'inventario e secondo set fatti; code review (10 rilievi, tutti corretti) e
  simplify applicati; giro finale dell'inventario in corso (`uv run --with ijson python
  tests/simulation/benchmark/radar_inventory.py`, ~30 min) → `radar/inventory.{md,json}`.
- PROTO-02: secondo set congelato (`protocol/holdout2.lock.json`, `24974f9b…`): CallCenter
  (completa) + Road Traffic Fines con la copia `Trafic` di DAS-RP (parziale). Nessun sintetico
  indipendente nel radar (DAS-RP `data_attribute_log` è Loan_Application): la categoria la copre
  GT-01. PROTOCOL.md §10 (ruolo di ogni voce) e §11 (CF-01), confronti appaiati nel §1.
- Da fare dopo il giro: rileggere il report, aggiornare i numeri del §10 se cambiano, PLAN, LOG,
  PR, CI, merge. Scelta del set e soglia dell'1% per la direzione presentate a Sohayb («procedi»).

## Ultima misura

ENG-01: harness B2 sullo stack reale prima e dopo, `baseline.json` identico bit per bit
(SHA-256 `4e4fce5d…`, 9/9 dentro), anche dopo il merge con VAL-01. G3: il "B = A" di
SIM-36 resta migliore di ogni scenario SIMOD, salvo BPIC 2017 W con ritardi estranei su
RED e W1. B6: what-if 10 × 1.000 casi in 11-26 s.

## Research Radar (RAD-00 fatto il 2026-11-25)

Decisione di Sohayb: servono più dati; tutti i dataset si usano per la ricerca. Dettagli e
regole in [`RESEARCH_RADAR.md`](./RESEARCH_RADAR.md), punti nella sezione R di [`PLAN.md`](./PLAN.md).

```bash
uv run python scripts/fetch_datasets.py fetch --collection radar   # 33 voci, ~24 GB estratti, MD5 o commit
uv run python scripts/fetch_datasets.py list                       # colonna "radar"
uv run pytest --noconftest -q tests/simulation/test_dataset_manifest.py
```

- 21 dataset (BPIC 2017 completo, 2018, 2019; Sepsis; Hospital Billing; Road Traffic Fines;
  Helpdesk; 9 pacchetti OCEL 2.0; drift con verità nota; SimBank, ProCause; BPS Quality
  Framework) e 12 repository (AT-KDE, Kronos, AgentSimulator, ProSiT, DAS, POWL,
  cdrift-evaluation, SimOC, generatore Declare, SimPy, salabim, QueueSim).
- **Collezione separata:** non è sviluppo né holdout. Gli holdout di PROTO-01 restano chiusi.
  Esclusi i BPIC 2015 del pacchetto OCEL. Prima di usare un log: RAD-01 (deduplica per hash e
  nome; ProCause contiene BPIC 2012/2017, alcuni pacchetti possono contenere i log di Camargo)
  e PROTO-02 (dichiarazione in `PROTOCOL.md`, secondo holdout congelato).
- **Da verificare in RAD-01/PROTO-02:** che Sepsis e Hospital Billing non vengano dallo stesso
  ospedale di BPIC 2011 (holdout).
- **Non acquisiti:** CDLG e SSD. L'host `gitlab.uni-mannheim.de` ora è nell'ambiente BK-GPT,
  ma il server risponde 404 a ogni richiesta dalla sessione cloud (anche alla home): vanno
  scaricati dal computer di Sohayb e aggiunti al manifest con il commit. Anche Helpdesk
  originale (Mendeley) e ProcessLog restano fuori.
- **Corretto il 2026-11-25:** `DELIR_AUTH_PROVIDER` si normalizza una volta in `Settings`
  (prima `Supabase` passava l'avvio e poi ogni token Supabase riceveva 401).

## ENG-01 (fatto il 2026-11-25, `feat/sim-engine-interface`)

Fra l'IR e il motore c'è una sola porta: `backend/simulation/engine/`. Prosimos 2.1
è un adattatore dietro di essa e la CI blocca chi lo importa da fuori.

```bash
uvx --from ast-grep-cli==0.51.3 ast-grep scan --error --rule .ast-grep-rules/python-engine-outside-adapter.yml backend/   # 0 rilievi
eval "$(scripts/vpt_stack.sh env)" && uv run pytest -q tests/simulation/test_engine_interface.py
uv run python tests/simulation/benchmark/eval_harness.py --out /tmp/b2    # baseline.json identico a main
```

- **Interfaccia** (`engine/__init__.py`): `SimulationEngine` (Protocol) con i verbi
  valida (`prepare_bpmn`, `validate`, `compatibility_report`), compila (`compile`),
  esegue (`run`), annulla (`cancel`), risultati (`read_log`, `resource_pool`,
  `summarize_run`, `summarize_events`); tipi neutri `LogEvent`, `after_warmup`,
  `EngineError`/`EngineCancelled`/`EngineLogError`, alias `CompiledScenario`,
  `EngineRunRequest`, `EngineRunResult` dei modelli (invariati); registro `get_engine()`,
  un'istanza per nome.
- **Adattatore**: `engine/prosimos.py` più i moduli che sanno di Prosimos
  (`prosimos_adapter`, `bpmn_normalizer`, `compatibility`, `ir/compile`,
  `log_processor`). All'import carica solo `ir.compile`: il test del contratto gira
  nel venv del runner senza httpx (c'è un test che lo controlla).
- **Regola** `python-engine-outside-adapter` (bloccante in CI): `prosimos`,
  `pix_framework` e i moduli dell'adattatore, import assoluti e relativi. Provata nei
  due sensi: 11/11 import vietati presi, 7/7 leciti no.
- **Nomi storici rimasti** perché i test (non modificabili) li sostituiscono:
  `service.run_prosimos_simulation`, `routes/eventlog.parse_prosimos_log`,
  `ir.compile_for_prosimos` (risolto dal registro). Test e script in `scripts/`
  importano ancora l'adattatore: sono fuori dalla regola (solo `backend/`).
- **Annulla**: c'è nell'interfaccia e nei test, ma il worker non lo usa. Il runner
  HTTP non sa fermare un calcolo: annullare libera il posto mentre il runner lavora
  ancora (oltre `SIMULATION_MAX_CONCURRENT_RUNS`). Collegarlo richiede un endpoint di
  stop nel runner (seguito per ENG-02).
- **Misura**: harness B2 prima e dopo, `baseline.json` SHA-256 `4e4fce5d…` identico
  bit per bit (9/9 dentro). Il file in `b2/baseline.json` del repo (`24809a7f…`) è
  vecchio di IMP-01: differisce solo per `import_notes` 4 → 5 sulle 4 Procure_to_Pay.
  Suite intera 3018 passati; `tests/simulation` + `tests/eventlog` 848; contratto nel
  venv del runner 32/32.
- **Per ENG-02**: un motore nuovo è una classe che rispetta `SimulationEngine`,
  registrata in `_engine`; `simulation_runs.engine` salva già il nome.

## PROTO-01 (fatto il 2026-11-25, PR #190)

Il protocollo di G3b è in [`PROTOCOL.md`](./PROTOCOL.md); in codice
`tests/simulation/benchmark/protocol.py`, test in `test_protocol.py` (124).

```bash
uv run python scripts/fetch_datasets.py fetch bpic2012 bpic2013-incidents
uv run python tests/simulation/benchmark/protocol_properties.py     # identificabilità dei 25 log di sviluppo
uv run pytest --noconftest -q tests/simulation/benchmark/test_protocol.py
```

- **Holdout congelati prima di ogni misura** (commit `476e705`): 6 log, lucchetto
  `protocol/holdout.lock.json`, impronta `1cfaa147…` scritta in PROTOCOL.md. Production,
  ConsultaDataMining, PurchasingExample, confidential_2000 (pacchetto Camargo 2022) e BPIC
  2015 Municipality 1, BPIC 2011 Hospital (4TU). Nel repo solo gli hash.
- **Guardia:** audit hook in `selection_phase()`, attivo per tutti i test del benchmark
  (`conftest.py`): chiude per nome, file derivati, cartelle dei dataset holdout (715/715 file
  del pacchetto Camargo), collegamenti; fase per thread. Il test sui nomi copre il codice
  di `tests/simulation`, `backend/simulation`, `backend/eventlog`, `scripts`. Si apre solo
  con `final_evaluation(<impronta>)`, una volta, alla fine di G3b.
- **Identificabilità** (`protocol/identifiability.md`): i 3 log del paper e i 20 sintetici
  validano tutte le metriche osservabili; BPIC 2012 no su W1, NGD, RED (6% tagliati) e durate
  (inizio sul 43%); BPIC 2013 no su W1, NGD, RED, CAR e durate, sì su AED, CED e risorse.
- **Per G3b:** punti d'ingresso in `selection_phase()`, log da `development_logs()`, scelta
  sulla validazione (`train_validation`, ultimo 20% del train), schede di go/no-go (§7) in
  `LOG.md` prima della misura, budget del §6.
- **Confermati da Sohayb (2026-11-25):** soglie del §4 (5% tagliati, 95% coperture, arrivi
  ×2, 30 casi), budget del §6, go/no-go del §7.

## VAL-01 (fatto il 2026-11-25, `feat/sim-formal-validation`, PR #189)

All'import e prima di ogni run DeliR verifica che ogni caso possa finire: niente
deadlock né livelock, fine raggiungibile da ogni stato, uscita da ogni ciclo con
probabilità > 0, ripetizioni attese finite. Meta confermata da Sohayb il 2026-11-25.

```bash
uv run pytest --noconftest -q tests/simulation/test_soundness.py          # 51 test, < 2 s
eval "$(scripts/vpt_stack.sh env)" && uv run pytest -q tests/simulation/test_prosimos_import_api.py
npx playwright test e2e/simulation-import-validation.spec.ts              # DELIR_UX_SHOTS=docs/vpt/ux/val-01
PYTHONPATH=. uv run python e2e/fixtures/val-01/generate.py                # risposte vere per l'e2e (serve lo stack)
```

- **Misura:** 19/19 scenari del dataset e 8/8 scenari SIMOD validi di G3 passano;
  AcademicCredentials `_diff` e `_fuzz` rifiutati sul gateway `node_59fc62b1…`;
  < 0,1 s e ≤ 119 stati per scenario. Suite `tests/simulation` sullo stack: 812 passati.
- **Metodo** (`backend/simulation/ir/soundness.py`): gioco dei gettoni a passo
  massimo (scattano insieme tutti gli elementi abilitati: il verdetto non dipende dai
  nomi), rami a probabilità 0 esplorati come impossibili per nominare la decisione che
  chiude il ciclo; `check_soundness(..., expected=True)` dà le esecuzioni attese per
  attività (catena assorbente). Limiti: 8 gettoni per flusso, 50.000 stati, 4096
  combinazioni per passo, 10 rami per inclusiva; oltre, verifica incompleta: l'import
  avvisa (`soundness_unverified`) ma tiene i blocchi già provati.
- **Dove si applica:** `import_prosimos` e `scenario_builder` (bozze, what-if) via
  `require_sound`; `UnsoundProcessError` non è un `ValueError` e arriva al gestore comune
  → 400 `process_cannot_finish` su import e run. Nella UI il motivo è in chiaro con
  «Cosa fare» a capo; i file che l'editor legge da solo passano dalla verifica del server.
- **Da sapere per B3.3:** «supera VAL-01» = `require_sound(model, bpmn)` senza eccezioni.
  Regole e escalation: ogni ramo possibile (nessuna attesa calcolata). Inclusive: ogni
  combinazione non vuota dei rami (Prosimos non documenta la sua semantica).
- **Seguiti proposti (non fatti):** messaggi del server solo in italiano (come le note
  di IMP-01); un solo parser BPMN con `flow_graph` (ingressi, nomi, eventi di bordo);
  endpoint di sola verifica per l'editor invece dell'import completo.

## SIM-36b (fatto il 2026-11-24, `feat/sim-benchmark-train-test`)

Baseline "B = A" sui 3 log reali train/test del paper (A = train, B = test): il banco
A → B che G3 e B3 devono battere. Per rifarla (≈11 s, senza rete):

```bash
uv run python tests/simulation/benchmark/run_baseline.py AcademicCredentials BPIC_2012_W BPIC_2017_W
```

- Misura (seed 20261124 × 10, ore): W1 28,8 ± 3,6 / 28,1 ± 2,0 / 30,6 ± 1,5; RED 25,9 /
  10,1 / 11,4; AED 62,3 / 29,7 / 42,8. Contro lo scenario SIMOD del paper simulato da B2
  "B = A" vince 17 confronti su 18 con intervalli separati (pari su CAR di
  AcademicCredentials). Bit per bit su due passate; misure SIM-36 dei BPIC identiche.
- `sim36/baseline.md` contiene la tabella "B = A" contro SIMOD per log e metrica; il
  confronto si fa solo con lo stesso seed e repliche di `b2/baseline.json` (`--b2`).
- BPIC 2013 incidents: `unsuitable_for_a_to_b` in `benchmark_datasets.py`, nel JSON e
  nella tabella. Resta misurato, nessuna meta lo usa.
- **Per G3:** `g3/evaluate.py::naive_metrics` rifà lo stesso gemello; dopo il merge di
  `main` può usare `run_baseline.measure(log, ...)["metrics"]`. `within_intervals` in
  `eval_harness.py` è identica a quella di G3 (stesso hunk): il merge non confligge.

## IMP-01 (fatto il 2026-11-24, `feat/sim-import-expon-warning`)

L'import avvisa quando Prosimos 2.1 renderà gli arrivi più fitti del file. Meta
raggiunta: avvisano le 4 varianti di Procure_to_Pay, nessuno dei 15 altri scenari;
lo scenario resta com'era (arrivi identici nell'IR e nel JSON ricompilato).

```bash
uv run pytest --noconftest -q tests/simulation/test_prosimos_import.py      # 19 scenari + golden
eval "$(scripts/vpt_stack.sh env)" && uv run pytest -q tests/simulation/test_prosimos_import_api.py
npx playwright test e2e/simulation-import-arrivals.spec.ts                  # DELIR_UX_SHOTS=docs/vpt/ux/imp-01 per gli screenshot
```

- **Regola:** pix_framework 0.15 estrae da `expon(loc=min, scale=mean-min)` e scarta
  (ricampiona) i valori oltre il massimo: media prodotta
  `min + s - R·e^(-R/s)/(1-e^(-R/s))`, `R = max-min`. Si avvisa se è più bassa di oltre
  il 10% della media scritta. Procure_to_Pay: 1805 s scritti, 1240,5 s prodotti
  (campionati: 1241,8), +45% di casi. Nessun avviso se gli arrivi li genera il runner
  (fasce o ritmi per mese).
- **Dove vive:** `prosimos_exponential_mean`/`_arrival_notes` in
  `backend/simulation/ir/from_prosimos.py` (nota `warning`, topic `arrivals_faster`) e
  `arrivalsRunFaster`/`draftArrivalsRunFaster` in `simulationScenario.ts` per l'editor.
  Le due copie le tiene uguali `tests/fixtures/simulation/arrivals_truncation_golden.json`.
- **UI:** nel pannello d'import "Da verificare" senza la parola "adattamenti"
  (nuovo tipo di nota `warning`: lo scenario non cambia); nell'editor un avviso in
  Arrivi dei casi con il bottone "Porta il massimo a …" (5 volte la media) e un toast
  all'import.
- **Trovato per strada:** col file vero il consulente veniva fermato prima dell'avviso
  da una richiesta di associare 3 ID tecnici (porte di sola unione). Ora il template
  del server elenca le porte di unione (`merges`) e il client non le chiede più.
  Corretto anche `withArrival`, che perdeva i ritmi per mese a ogni modifica degli arrivi.
- **Seguiti proposti (non fatti):** la frase sotto la media degli arrivi dice ancora
  "segue una distribuzione esponenziale" e mostra "30.1" col punto; i dettagli delle
  note del server sono solo in italiano; un run lanciato fuori dalla UI non riceve
  l'avviso (servirebbe una nota a livello di run).

## B6 (fatto il 2026-11-24, `spike/sim-throughput`)

Throughput del simulatore (G2). Meta raggiunta: un what-if da 10 ripetizioni × 1.000
casi va dalla richiesta ai KPI e ai log riletti in 11-26 s (4 CPU), con risultati
identici bit per bit.

```bash
scripts/vpt_stack.sh start && eval "$(scripts/vpt_stack.sh env)"
uv run python tests/simulation/benchmark/throughput.py --check   # 1, 2, 4 worker × 3 giri, ~4 min
```

- **Percorso:** API uvicorn vera (`backend.app`), coda Postgres, worker in processo,
  runner Prosimos 2.1 con N worker gunicorn e `SIMULATION_MAX_CONCURRENT_RUNS=N`;
  `POST simulation-runs` con `replications: 10` come il pannello. Scenario
  Loan_Application (sintetico del paper) tradotto nei campi del pannello, seed 20261124.
- **Misura finale** (`tests/simulation/benchmark/b6/throughput.md`): 1 worker 22,9-26,1 s
  (23-26 run/min), 2 worker 14,3-14,5 s (41-42), 4 worker 11,3-11,5 s (52-53). Prima
  (`throughput-before.md`): 4 worker 11,5-16,3 s, irregolare.
- **Fasi per run** (riga di log `simulazione N: in coda …, motore …, analisi …,
  salvataggio …`, `_PhaseTimer`): motore 1,5-1,9 s, analisi 0,2-0,5 s, salvataggio
  0,1-0,3 s. Il motore e' tutto Prosimos (campionamento scipy): il runner non aggiunge
  nulla. Con 4 worker su 4 CPU siamo vicini al minimo (~3 ondate).
- **Cambiato:** una richiesta di run sveglia subito il giro della coda
  (`wake_simulation_worker`), che riempie i posti liberi; prima gli altri posti
  aspettavano fino a 10 s. Un run diventa `completed` nella stessa transazione dei suoi
  KPI e del suo log (prima chi leggeva poteva trovare "completed" senza log: 404).
- **Risultati invariati:** impronte SHA-256 di KPI e log in `b6/fingerprints.json`
  (`--check`); harness B2: `baseline.json` identico (`24809a7f…`), 9/9 dentro.
- **Da sapere:** l'export del log costa ~0,3 s a run (download su richiesta); il
  risveglio vale nello stesso processo: con piu' processi API un posto liberato da un
  altro processo aspetta ancora il giro (servirebbe `LISTEN/NOTIFY`). B7 puo' contare
  su ~50 run/min da 1.000 casi con 4 worker.

## G3 spike SIMOD (fatto il 2026-11-24)

Decisione e numeri nella voce G3 di [`LOG.md`](./LOG.md); tabelle complete in
`tests/simulation/benchmark/g3/results.md`. In breve: **SIMOD sì come motore di discovery,
a condizioni** (servizio in background, variante fissi + ritardi estranei, controllo dei
cicli senza uscita, "validato" solo se batte "B = A").

```bash
scripts/vpt_stack.sh start && eval "$(scripts/vpt_stack.sh env)"
tests/simulation/benchmark/g3/discover.sh all     # SIMOD 5.2.1, venv in /var/tmp/delir-vpt-stack/simod-venv, serve Java
uv run python tests/simulation/benchmark/g3/evaluate.py          # ~20 min, 10 scenari × 10 repliche
uv run python tests/simulation/benchmark/g3/evaluate.py --report-only   # solo results.md
```

Da sapere per B3 (e B5):

- **Asticella:** il "B = A" di SIM-36 con A = train e B = test (`run_baseline.NaiveTwin`).
  Vince su quasi tutto; SIMOD lo batte solo su BPIC 2017 W con i ritardi estranei (RED 8,1
  contro 11,4, W1 17,9 contro 30,6). AED e CAR restano dell'ingenuo ovunque.
- **Punto di partenza:** `g3/discovered/<log>_extr` (BPIC 2012 W e 2017 W); per
  AcademicCredentials SIMOD lascia un ciclo senza uscita e `extr` crolla.
- **Harness:** `Scenario(name, "real-life", source=cartella)` valuta uno scenario esterno
  con lo stesso log di test; `within_intervals` è la regola "pari" condivisa con B2.
- La discovery non è riproducibile (nessun seed in SIMOD): gli scenari usati sono nel repo.
- **Per SIM-36b:** G3 ha già misurato "B = A" con A = train e B = test, riusando
  `run_baseline.NaiveTwin` (righe "gemello ingenuo" di `g3/results.md`, `naive_metrics` in
  `g3/evaluate.py`): SIM-36b lo porta nel formato e nella cartella del benchmark.
- **Per la meta di B3** (batte "B = A" su W1, RED e AED senza sovrapposizione): nessuno
  scenario SIMOD ci arriva; il migliore, BPIC 2017 W con ritardi estranei, batte su RED e
  W1 ma perde su AED (106,3 ± 9,3 contro 42,8 ± 4,0).
- **Proposto, non fatto:** un punto Prod perché l'import rifiuti (o segnali) un gateway che
  torna indietro con probabilità 1 e uscita 0.

## CAL-01 (fatto il 2026-11-24, PR #172)

Gli scenari SIMOD con calendari FUZZY si importano, si ricompilano identici e girano
sul runner Prosimos 2.1 dello stack. Misura finale e iterazioni nella voce di `LOG.md`.
Da sapere per chi tocca i calendari:

- Nell'IR la probabilità sta solo su `CalendarPeriod`; fasce degli arrivi e delle
  durate derivano da `WeekPeriod` e non la accettano.
- Prosimos considera libera una risorsa se lo dice la disponibilità **o** il carico
  (`FuzzyModel.is_available`): un carico a 1 annulla la disponibilità.
- Il motore fuzzy riporta ogni orario all'inizio della sua fascia: l'IR rifiuta orari
  fuori dal granulo. SIMOD scrive la fine a mezzanotte come `00:00:00`; l'IR la tiene
  come `23:59:59.999999` e la riscrive `00:00:00`.
- Una fascia senza probabilità Prosimos la leggerebbe 0: l'import la rifiuta.
- Il test sul runner HTTP gira solo con `DELIR_TEST_PROSIMOS_URL=$PROSIMOS_BASE_URL`.
- Per rilanciare SIMOD: venv Python 3.12, `pip install` del repo SIMOD dalla cache
  (`scripts/fetch_datasets.py fetch simod`), serve Java.

## CI

`main` è tornato verde il 2026-11-24 con #170: mobile-safari 4/4 era rosso dal merge di
#168 perché, su iPhone, la barra degli strumenti del canvas copriva l'evento che il
test `event type selection…` cliccava. Il test ora tocca l'arco visibile.

## Ambiente

- **Stack reale:** `scripts/vpt_stack.sh start` avvia Postgres 16 con le migrazioni e
  il runner Prosimos 2.1 (Python 3.12), senza Docker. Sostituisce la ricetta manuale
  di Postgres.
- Sessioni cloud sull'ambiente **BK-GPT** (consente zenodo.org e data.4tu.nl).
- I test che non toccano il database girano con `uv run pytest --noconftest ...`;
  la suite completa richiede lo stack reale, Docker (`cd ops && docker compose up -d`) o la CI.
- Playwright in cloud: il repo fissa una versione diversa da quella preinstallata.
  Usa una config locale non committata che estende `playwright.config.ts` con
  `launchOptions.executablePath: '/opt/pw-browsers/chromium'`.

## Decisioni aperte per Sohayb

- Copiare comunque nel repo pubblico BPIC 2012/2013/2020 e Prosimos?
- Confermare le mete marcate *proposta* dei punti P0, B3.1-B3.4, SEL-01, ENG-02, PERF-01
  e CF-01 in `PLAN.md`.

Decise da Sohayb il 2026-11-24 (motivi in `LOG.md`):

- SIMOD resta un benchmark; la sostituzione dipende da G3b. Il motore di esecuzione non è
  dato per scontato (ENG-01, ENG-02). Ogni componente entra solo con evidenza sperimentale.
- Validazione formale all'import (VAL-01), che copre anche i cicli senza uscita di G3.
- Prosimos (2026-11-25): resta il motore per l'MVP e i test del prodotto con le aziende;
  dopo l'MVP si sostituisce (ENG-02). Nessun contatto con i titolari del codice.
- Nessun log escluso dal benchmark: le metriche non identificabili si dichiarano NOT
  VALIDATED (PROTO-01). Questo supera "BPIC 2013 non adatto" della decisione precedente.

- Benchmark A→B: i 3 log reali train/test del paper sono il banco principale
  (SIM-36b); BPIC 2012 resta; BPIC 2013 incidents non serve a giudicare un twin.
- Meta di B3 confermata, con "batte B = A" misurato sui 3 log train/test.
- Arrivi `expon` di Procure_to_Pay: l'import avvisa il consulente (IMP-01).
- `DELIR_ADMIN_TOKEN` in staging e prod e la VM per l'isolamento fra clienti: li
  fa Sohayb; nessun agente può farlo dal repo.

## B2 (fatto il 2026-11-24, PR #174)

Le tre mete sono raggiunte. Per ripartire (B3, B5, G3, VPT-10):

```bash
scripts/vpt_stack.sh start && eval "$(scripts/vpt_stack.sh env)"
uv run python tests/simulation/benchmark/eval_harness.py          # 19 scenari, ~5 min
uv run python tests/simulation/benchmark/eval_harness.py Pharmacy --out /tmp/b2   # una parte
```

- **Percorso:** import da `prosimos-import`, run da `simulation-model-runs` (coda,
  worker, runner Prosimos 2.1), log degli eventi e KPI riletti dall'API. Casi e inizio
  come il log di riferimento; seed `20261124 + replica`; 10 repliche come il paper.
- **Metriche:** `tests/simulation/benchmark/log_distance.py`, port di
  `log-distance-measures` 2.2 (Apache 2.0). `test_log_distance.py` le confronta con i
  numeri della libreria (`fixtures/log_distance_reference.json`, rigenerabile in un
  venv 3.12 con `log_distance_reference.py`) e, se c'è la cache di
  `extraneous-delays-outputs`, riproduce la riga `original` del paper dai suoi log.
- **Uscite:** `tests/simulation/benchmark/b2/baseline.json` (bit per bit con lo
  stesso seed), `baseline.md` (tabella), `paper-comparison.md`.
- **Repliche del paper: 10** (script `infsys-real-life-evaluation.py`, upstream commit
  `26c88a0^`). W1 del cycle time il paper non lo pubblica: riferimento ricavato dai
  suoi 10 log `sim_original` (`fixtures/paper_original_cycle_time_w1.json`).

### Misura finale (seed 20261124, 10 repliche)

- Meta 1: due passate complete, stesso SHA-256 di `baseline.json`
  (`24809a7f…`); con seed diverso il file cambia (`test_same_seed_same_baseline_bit_for_bit`).
- Meta 2: 9/9 dentro, vedi `b2/paper-comparison.md`.
- Meta 3: 16 sintetici in `b2/baseline.md`.

### Da sapere per B3 e B5

- **Procure_to_Pay** (tutte e 4 le varianti) ha W1 ~340-360 h e CAR ~250 h contro il
  proprio log: l'arrivo `expon [1805, 5, 3600]` nel log di riferimento ha intervalli
  quasi costanti (mediana 1802 s, metà centrale 1789-1822 s), mentre Prosimos 2.1 lo
  legge come esponenziale di media 1805 tagliato a [5, 3600] (pix_framework 0.15,
  `expon(loc=min, scale=mean-min)`): arrivi più fitti, code più lunghe. Il JSON arriva
  al runner identico; lo scarto è della semantica del motore che ha generato il log.
  Va tenuto fuori dai confronti "DeliR contro verità" di B3/B5 o letto con questa nota.
- **Loan_Application** ha W1 3-9 h e CAR 1-3 h: arrivi fissi uguali al riferimento,
  la differenza nasce dopo l'arrivo. Non indagata oltre (B2 non ha soglie sui sintetici).
- Il KPI "cycle" di DeliR misura dal primo arrivo (abilitazione) all'ultima fine; le
  distanze del paper dal primo inizio. L'harness verifica che il KPI salvato coincida
  con il log riletto, nella definizione del KPI.

### Richieste per Sohayb

- Decidere se l'import (CAL-01 o un punto nuovo) debba segnalare gli arrivi `expon`
  con media vicina al massimo, che Prosimos 2.1 tronca in modo diverso dai motori
  precedenti.

## SIM-36 (fatto il 2026-11-24, PR #178)

Baseline "B = A" su BPIC 2012 e BPIC 2013 incidents con le metriche di B2, salvata in
`tests/simulation/benchmark/sim36/` (solo metriche: i log 4TU non entrano nel repo).
Per rifarla:

```bash
uv run python scripts/fetch_datasets.py fetch bpic2012 bpic2013-incidents
uv run python tests/simulation/benchmark/run_baseline.py bpic2012
uv run python tests/simulation/benchmark/run_baseline.py bpic2013_incidents
```

- Misura (seed 20261124, 10 repliche, ore): BPIC 2012 W1 16,9 ± 1,5, AED 60,3 ± 3,3,
  NGD 0,055; BPIC 2013 W1 384 ± 8, AED 334 ± 16, NGD 0,329. Bit per bit su due passate.
  Tabella completa e lettura in `docs/simulation-benchmark.md`.
- **Per B3 e G3:** un twin calibrato su A batte la baseline se il suo intervallo sta sotto
  quello di "B = A". Su BPIC 2013 il periodo B è troncato dalla fine del log (casi visti
  al massimo 20 giorni): W1 premia chi tiene conto del taglio. AED e CAR vengono dalla coda
  2010-2011 di A.
- BPIC 2013 prima si leggeva con 0 eventi (ciclo di vita = sottostato): ora la mappatura
  è per dataset in `benchmark_datasets.py`.

## UX-01 (fatto il 2026-11-24, PR #173)

- La vista "Reale contro simulato" si legge senza gergo; la statistica è in
  "Dettagli per specialisti". Screenshot in `docs/vpt/ux/ux-01/`.
- Misura: e2e `simulation-eventlog` 14/14 (chromium e mobile-chrome, axe pulito, controllo
  anti-gergo), vitest simulazione 438/438.
- Seguito proposto (non fatto, fuori scopo): sotto i 1199px ogni pannello dello studio finisce
  sotto il disegno; UX-01 sposta prima solo l'event log (`.sim-studio-dock.is-event-log` in
  `studio.css`). Estenderlo a tutti i pannelli di analisi richiede un gate UX su ciascuno.
- Seguito proposto: un `formatSigned` comune (oggi copiato in `ValidationReport`,
  `decisionRecord`, `ScenarioWorkspacePanel`, `ReplicationDelta`).
