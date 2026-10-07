# Runner Prosimos di DeliR

Prosimos 2.1.0 dietro la stessa API che `backend/simulation/prosimos_adapter.py`
usa oggi. Sostituisce il microservizio upstream patchato (Prosimos 1.2.6,
Python 3.9): il perché è in [docs/simulation-prosimos-2x-spike.md](../../../docs/simulation-prosimos-2x-spike.md).

## API

| Metodo | Percorso | Note |
| --- | --- | --- |
| `POST` | `/api/simulate` | multipart: `modelFile`, `simScenarioFile`, `numProcesses`, `startDate`, `seed` opzionale |
| `GET` | `/api/simulationFile?fileName=` | solo `stats_*.csv` / `logs_*.csv` scritti dal runner; scadono dopo `RUNNER_FILE_TTL_SECONDS` |
| `GET` | `/health` | versione del motore e di Python |

La risposta di `/api/simulate` ha le chiavi del microservizio upstream
(`ResourceUtilization`, `IndividualTaskStatistics`, `OverallScenarioStatistics`
come stringhe JSON doppiamente codificate, `StatsFilename`, `LogsFilename`) più:

- `Seed`: il seed usato. Se la richiesta non ne manda uno, il runner ne sceglie
  uno nuovo e lo restituisce: ogni run si può rifare identico.
- `EngineVersion`: la versione di Prosimos.

Errori: `400` per input non valido (parametri, BPMN o scenario rifiutati dal
motore), `500` per il resto, sempre con `errorMessage` leggibile.

## Avvio

```bash
cd ops/prosimos
docker build -f runner/Dockerfile -t delir-prosimos-runner .
docker run --rm -p 5000:5000 delir-prosimos-runner
```

Variabili: `GUNICORN_WORKERS` (6, un run concorrente per worker),
`GUNICORN_TIMEOUT` (1800 s), `RUNNER_FILE_TTL_SECONDS` (3600),
`RUNNER_MAX_CASES` (100000).

I worker sono sync di proposito: Prosimos usa `random` e `numpy.random` globali,
e un worker che serve un run alla volta non mescola lo stato fra run.

## Test

Nell'ambiente del runner (Python 3.11 o 3.12), non nel venv del backend:

```bash
pip install -r ops/prosimos/runner/requirements.txt pytest
pytest ops/prosimos/runner
```

I test riusano lo scenario e i controlli di `ops/prosimos/spike/contract_spike.py`:
forma della risposta, seed riproducibile, run senza seed ripetibile, routing
condizionale, attributi che cambiano nel processo, nomi file protetti, errori.
