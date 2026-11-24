# Dove siamo adesso

Aggiornato: 2026-11-24, dopo B1a e B1b (PR #170, che chiude anche #169) e lo stack
reale per il simulatore (`scripts/vpt_stack.sh`, PR #171).

## Punti attivi

Tre punti in parallelo, una sessione ciascuno (regole in "Più agenti in parallelo"
di [`WORKFLOW.md`](./WORKFLOW.md)). Ognuno aggiorna solo la propria sezione qui sotto.

- **B2** harness di valutazione: meta decisa da Sohayb, vedi la sezione B2.
- **CAL-01** calendari FUZZY di SIMOD: vedi "Come riprendere CAL-01".
- **UX-01** leggibilità di "Reale contro simulato".

## Ultima misura

B1b: e2e `e2e/simulation-prosimos-import.spec.ts` 8/8 (chromium e mobile-chrome),
test API 4/4, unit 4/4; gate UX in `docs/vpt/ux/b1b-server-import/`.
CONF-02: e2e `simulation-eventlog` 12/12 su chromium e mobile-chrome, axe pulito;
screenshot in `docs/vpt/ux/conformance/`. CONF-01: LoanApp 500/500 casi conformi.

## Come riprendere CAL-01

1. Leggi [`WORKFLOW.md`](./WORKFLOW.md) e la voce più recente di [`LOG.md`](./LOG.md).
2. Scarica Prosimos 2.1 (`uv run python scripts/fetch_datasets.py fetch prosimos`) e
   leggi come rappresenta ed esegue i calendari FUZZY.
3. Serve uno scenario SIMOD con calendari FUZZY scoperto sul dataset: il test di
   import e round trip va scritto per primo e deve fallire.
4. Estendi IR, `from_prosimos.py` e `compile_for_prosimos`; poi run sul runner.

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
  ±10%). Quella di B2 è decisa (2026-11-24).

## B2 (in corso dal 2026-11-24, sessione su `feat/sim-eval-harness`)

Meta in [`PLAN.md`](./PLAN.md). Cosa si sa già, per partire subito:

- Si misura sullo stack reale: `scripts/vpt_stack.sh start`, poi
  `eval "$(scripts/vpt_stack.sh env)"` (vedi "Stack reale" in `WORKFLOW.md`).
  Il percorso è quello del prodotto: import (`prosimos-import`, PR #170) → database
  → run dalla coda → runner Prosimos 2.1 → log e KPI letti dal database.
- Il paper calcola le distanze con `log-distance-measures` 2.2 (PyPI). Richiede
  Python `>=3.11,<3.13`: il backend è sulla 3.14, quindi o gira in un venv 3.12
  come il runner, o le formule si portano nel nostro codice con un test che dia
  gli stessi numeri della libreria. Il codice del paper è Apache 2.0
  (`github.com/AutomatedProcessImprovement/extraneous-activity-delays`); la
  licenza della libreria va verificata prima di copiarne codice.
- Nel codice del paper `num_evaluation_simulations` vale 3 di default; il numero
  di repliche usato per `paper-results` va confermato (script di valutazione su
  Zenodo, `extraneous-delays-outputs`).
- `paper-results/real-life-evaluation/metrics.csv`: colonne `relative_*` (RED) e
  `absolute_*` (AED), media e `cnf` (intervallo) per run; la riga da riprodurre è
  `<log>_original`. `metrics-cycle-time.csv` ha i quantili del cycle time.
  I `metrics.csv` dei sintetici misurano la scoperta dei ritardi (B5), non la
  fedeltà.
- Esistono già `tests/simulation/benchmark/benchmark_metrics.py` (W1 e W1
  relativo) e `run_baseline.py` (gemello ingenuo su BPIC): riusali dove servono.
