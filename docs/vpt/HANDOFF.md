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

Meta in [`PLAN.md`](./PLAN.md). Stack: `scripts/vpt_stack.sh start`, poi
`eval "$(scripts/vpt_stack.sh env)"`.

### Punti aperti chiusi (2026-11-24)

- **Repliche del paper: 10.** Lo script `tests/infsys-real-life-evaluation.py`
  (cancellato dal repo upstream nel commit `26c88a0`, si legge con `git show
  26c88a0^:tests/infsys-real-life-evaluation.py`) fa `for i in range(10)`, simula
  tanti casi quanti il log di test a partire dal suo primo inizio, e calcola media e
  intervallo t di Student al 95% (`ddof=1`). In `extraneous-delays-outputs` ci sono
  infatti `<log>_sim_original_0…9.csv`.
- **Licenza di `log-distance-measures` 2.2: Apache 2.0** (file `LICENSE` del repo
  `AutomatedProcessImprovement/log-distance-measures`, tag 2.2.0). Si può portare con
  attribuzione.
- **La libreria 2.2 riproduce il paper.** Sui 10 log `sim_original` del paper contro
  il log di test, in un venv 3.12 con `log-distance-measures==2.2.0`:

  | Log | RED | AED | W1 cycle time (ore, bin 1 h) |
  | --- | --- | --- | --- |
  | AcademicCredentials | 77,210731 ± 0,350470 | 132,824304 ± 26,745947 | 174,662060 ± 0,962148 |
  | BPIC 2012 W | 178,545369 ± 0,013214 | 223,843232 ± 8,437542 | 175,721102 ± 0,032542 |
  | BPIC 2017 W | 183,554654 ± 0,018163 | 296,035082 ± 9,530822 | 253,330301 ± 0,020749 |

  RED e AED coincidono con `paper-results/real-life-evaluation/metrics.csv` a tutte
  le cifre. Il paper non pubblica W1 del cycle time: il riferimento è questo, calcolato
  dai suoi 10 log con la stessa libreria (bin di un'ora, come SIMOD).

### Decisione sul calcolo delle metriche

Formule portate nel nostro codice (Python 3.14, senza scipy), con un test che dà gli
stessi numeri della libreria su log del repo; i valori della libreria si rigenerano in
un venv 3.12.

### Harness

`uv run python tests/simulation/benchmark/eval_harness.py [scenario ...]` (con lo
stack acceso e `eval "$(scripts/vpt_stack.sh env)"`): import da `prosimos-import`,
run da `simulation-model-runs` (coda e worker, runner Prosimos 2.1), log e KPI
riletti dall'API. Scrive `tests/simulation/benchmark/b2/baseline.json` e
`paper-comparison.md`. Formule in `log_distance.py`, test in `test_log_distance.py`.

### Misure

1. 2026-11-24, AcademicCredentials, seed 20261124, 10 repliche (4,7 s): RED 77,464 ±
   0,210 contro 77,211 ± 0,350 (dentro); AED 121,397 ± 23,249 contro 132,824 ± 26,746
   (dentro); W1 cycle time 174,837 ± 0,421 contro 174,662 ± 0,962 (dentro).

2. 2026-11-24, BPIC 2012 W (19,7 s) e BPIC 2017 W (48,7 s), stesso seed, 10 repliche:
   tutte dentro. 2012: RED 178,538 ± 0,020 contro 178,545 ± 0,013; AED 221,446 ± 8,148
   contro 223,843 ± 8,438; W1 175,710 ± 0,036 contro 175,721 ± 0,033. 2017: RED
   183,545 ± 0,019 contro 183,555 ± 0,018; AED 303,353 ± 9,738 contro 296,035 ± 9,531;
   W1 253,314 ± 0,033 contro 253,330 ± 0,021.
3. In corso: i 19 scenari due volte con lo stesso seed (meta 1).

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
