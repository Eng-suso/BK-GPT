# Dove siamo adesso

Aggiornato: 2026-11-24, dopo la chiusura in parallelo di SIM-36 (baseline "B = A", PR
#178), B6 (throughput, PR #179) e G3 (spike SIMOD). Ricomposto da chi ha chiuso l'ultimo
dei tre (G3).

## Punti attivi

Nessuno. SIM-36, G3 e B6 sono chiusi: prossimo secondo [`PLAN.md`](./PLAN.md) è **B3**
(discovery dei parametri), che parte dalla decisione G3 (sezione sotto).

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

## Ultima misura

G3, seed 20261124, 10 repliche sullo stack reale: SIMOD 5.2.1 a calendari fissi batte lo
scenario del paper su 4/4 metriche su BPIC 2012 W e 2017 W; il "B = A" di SIM-36 resta
migliore di ogni scenario SIMOD, salvo BPIC 2017 W con ritardi estranei su RED e W1.
B6: what-if 10 × 1.000 casi in 11-26 s. SIM-36: baseline in `tests/simulation/benchmark/sim36/`.

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

- Impostare `DELIR_ADMIN_TOKEN` in staging e prod: senza, le cancellazioni ora
  rispondono 403 (SEC-ADMIN).
- Copiare comunque nel repo pubblico BPIC 2012/2013/2020 e Prosimos?
- Confermare la meta marcata *proposta* di B3 in `PLAN.md` (gateway ±0,05, durate
  ±10%).
- Arrivi `expon` di Procure_to_Pay: vedi "Richieste per Sohayb" nella sezione B2.
- G3: aprire un punto Prod perché l'import rifiuti o segnali un gateway che torna indietro
  con probabilità 1 e uscita 0 (SIMOD lo produce su AcademicCredentials e oggi passa).
- G3: confermare le condizioni per SIMOD come motore di discovery (voce G3 di `LOG.md`),
  prima che B3 ci costruisca sopra.

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
