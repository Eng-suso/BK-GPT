# Dove siamo adesso

Aggiornato: 2026-11-24, dopo la chiusura in parallelo di B2 (harness di valutazione),
CAL-01 (calendari FUZZY di SIMOD, PR #172) e UX-01 ("Reale contro simulato"
leggibile, PR #173). Ricomposto da chi ha chiuso l'ultimo dei tre (B2).

## Punti attivi

Nessuno. Prossimi secondo l'ordine di [`PLAN.md`](./PLAN.md): **SIM-36** (baseline
pubblica su BPIC 2012/2013) e **G3** (spike SIMOD), in parallelo; poi **B3**. Tutti si
misurano con l'harness di B2 (sezione sotto).

## Ultima misura

B2, seed 20261124, 10 repliche sullo stack reale: `baseline.json` identico bit per bit
su due passate; 9/9 metriche dentro contro il paper sui 3 log reali; baseline dei 16
sintetici in `tests/simulation/benchmark/b2/baseline.md`. CAL-01 e UX-01: misure nelle
loro voci di [`LOG.md`](./LOG.md).

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
