# Runner Prosimos di DeliR

Prosimos 2.1.0 dietro la stessa API che `backend/simulation/prosimos_adapter.py`
usa oggi. Sostituisce il microservizio upstream patchato (Prosimos 1.2.6,
Python 3.9): il perché è in [docs/simulation-prosimos-2x-spike.md](../../../docs/simulation-prosimos-2x-spike.md).

## API

| Metodo | Percorso | Note |
| --- | --- | --- |
| `POST` | `/api/simulate` | multipart: `modelFile`, `simScenarioFile`, `numProcesses`, `startDate`, `seed` opzionale, `inlineLog=1` per avere il log nella risposta |
| `GET` | `/api/simulationFile?fileName=` | solo `stats_*.csv` / `logs_*.csv` scritti dal runner; scadono dopo `RUNNER_FILE_TTL_SECONDS` |
| `GET` | `/health` | versione del motore e di Python |

La risposta di `/api/simulate` ha le chiavi del microservizio upstream
(`ResourceUtilization`, `IndividualTaskStatistics`, `OverallScenarioStatistics`
come stringhe JSON doppiamente codificate, `StatsFilename`, `LogsFilename`) più:

- `Seed`: il seed usato. Se la richiesta non ne manda uno, il runner ne sceglie
  uno nuovo e lo restituisce: ogni run si può rifare identico.
- `EngineVersion`: la versione di Prosimos.
- `ArrivalBands`: quante fasce degli arrivi (`delir_arrival_bands`) il runner ha
  applicato. Gli istanti si contano dall'inizio chiesto, anche fuori dalle
  fasce: il runner non lascia che Prosimos lo sposti alla prima apertura.
- `ArrivalMonths`: quanti mesi con un ritmo proprio (`delir_arrival_months`,
  SIM-08b, mese → fattore) il runner ha applicato sopra le fasce. Senza fasce
  la sezione si rifiuta con un `400`: il backend le ricava dal calendario degli
  arrivi quando gli arrivi sono esponenziali.
- `DurationWindows`: quante attività hanno durate per ora d'inizio
  (`delir_duration_windows`, SIM-33b). Prosimos non lo sa fare: il runner
  avvolge `TaskEvent.__init__` e riscala la durata campionata
  (`duration_windows.py`). La patch è scritta per prosimos 2.1.0: con un'altra
  versione la sezione si rifiuta con un `400`.

- `EventLogCsv` (solo con `inlineLog=1`): il log degli eventi. L'adapter lo
  chiede sempre: con piu' repliche del runner un secondo `GET` del file puo'
  finire su un container che il file non l'ha.

L'adapter confronta questi conteggi con le sezioni che ha mandato e rifiuta un
motore che le ignorerebbe in silenzio. Rifiuta anche un motore che non dichiara
`EngineVersion` 2.x (la 1.2.6 accetta `branch_rules` e li ignora) e un run che
non restituisce il log: un run completato senza KPI non esiste.

Errori, sempre con `errorMessage` leggibile: `400` input non valido (parametri,
BPMN o scenario rifiutati dal motore), `401` token mancante o sbagliato, `413`
richiesta troppo grande, `504` run oltre la scadenza, `500` il resto.

## Avvio

```bash
cd ops/prosimos
docker build -f runner/Dockerfile -t delir-prosimos-runner .
docker run --rm -p 5000:5000 delir-prosimos-runner
```

Variabili: `GUNICORN_WORKERS` (6, un run concorrente per worker),
`GUNICORN_TIMEOUT` (1800 s), `RUNNER_FILE_TTL_SECONDS` (3600),
`RUNNER_MAX_CASES` (100000), `RUNNER_API_TOKEN` (vuoto = nessun controllo; con
un valore serve `Authorization: Bearer` su `/api/*`, lo stesso valore va in
`PROSIMOS_API_TOKEN` dell'app), `RUNNER_MAX_UPLOAD_BYTES` (20 MiB),
`RUNNER_RUN_TIMEOUT_SECONDS` (870: sotto i 900 s dell'app, cosi' il motivo arriva
prima del timeout HTTP e il worker si libera).

In sviluppo `scripts/dev.ps1` costruisce e avvia questo runner (immagine
`delir-prosimos-runner:dev`, container `delir-prosimos-runner-dev`): lo stesso
motore di staging e produzione.

I worker sono sync di proposito: Prosimos usa `random` e `numpy.random` globali,
e un worker che serve un run alla volta non mescola lo stato fra run.

## Test

Nell'ambiente del runner (Python 3.11 o 3.12), non nel venv del backend:

```bash
pip install -r ops/prosimos/runner/requirements-test.txt
pytest ops/prosimos/runner
pytest --noconftest tests/simulation/test_simulation_ir_engine.py
```

In CI li fa girare il job `prosimos-runner` (Python 3.12), separato dal job del
backend che gira sulla 3.14 e dove l'IR sul motore vero si salta.

I test riusano lo scenario e i controlli di `ops/prosimos/spike/contract_spike.py`:
forma della risposta, seed riproducibile, run senza seed ripetibile, routing
condizionale, attributi che cambiano nel processo, nomi file protetti, errori.
