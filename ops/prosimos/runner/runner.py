"""Runner Prosimos di DeliR: Prosimos 2.x dietro la stessa API che l'adapter usa oggi.

Sostituisce il microservizio upstream patchato (Prosimos 1.2.6, Python 3.9):
vedi docs/simulation-prosimos-2x-spike.md per il perche'.

API, compatibile con ``backend/simulation/prosimos_adapter.py``:

- ``POST /api/simulate`` (multipart): ``modelFile``, ``simScenarioFile``,
  ``numProcesses``, ``startDate`` e, in piu', ``seed`` opzionale. Risponde con
  ``ResourceUtilization``, ``IndividualTaskStatistics``,
  ``OverallScenarioStatistics`` (stringhe JSON, come upstream), ``StatsFilename``,
  ``LogsFilename``, e ``Seed`` / ``EngineVersion``.
- ``GET /api/simulationFile?fileName=...``: il CSV prodotto da un run.
- ``GET /health``: versioni di motore e runtime.

Il seed. Prosimos usa ``random`` e ``numpy.random`` globali e non ne espone uno.
Il runner li inizializza a ogni richiesta: con il seed ricevuto, oppure con uno
nuovo che restituisce. Cosi' ogni run, anche senza seed, si puo' rifare uguale.
Serve anche per un motivo meno ovvio: i worker gunicorn nascono per fork e
ereditano lo stesso stato casuale, quindi senza reinizializzazione due run in
worker diversi produrrebbero lo stesso campione. Un worker sync serve una
richiesta alla volta, quindi lo stato globale non e' condiviso fra run.
"""

from __future__ import annotations

import json
import os
import random
import re
import secrets
import shutil
import sys
import tempfile
import time
from importlib.metadata import version
from io import StringIO
from pathlib import Path

import numpy
import pandas
from flask import Flask, jsonify, request, send_file
from prosimos.exceptions import (
    InvalidBpmnModelException,
    InvalidLogFileException,
    InvalidSimScenarioException,
)
from prosimos.simulation_engine import run_simulation

DATA_DIR = Path(os.environ.get("RUNNER_DATA_DIR", tempfile.gettempdir())) / "delir-prosimos"
# I file restano quanto basta all'adapter per scaricarli subito dopo il run.
FILE_TTL_SECONDS = int(os.environ.get("RUNNER_FILE_TTL_SECONDS", "3600"))
MAX_CASES = int(os.environ.get("RUNNER_MAX_CASES", "100000"))
MAX_SEED = 2**32 - 1
_FILE_NAME = re.compile(r"^(stats|logs)_[A-Za-z0-9_]+\.csv$")
_INPUT_ERRORS = (InvalidBpmnModelException, InvalidLogFileException, InvalidSimScenarioException)

app = Flask(__name__)


class BadRequest(ValueError):
    """Input del chiamante non valido: 400 con il motivo."""


def engine_version() -> str:
    return version("prosimos")


def _seed_everything(seed: int) -> None:
    random.seed(seed)
    numpy.random.seed(seed)


def _parse_seed(raw: str | None) -> int:
    if raw is None or raw == "":
        return secrets.randbelow(MAX_SEED + 1)
    try:
        seed = int(raw)
    except ValueError as exc:
        raise BadRequest(f"seed non e' un intero: {raw!r}") from exc
    if not 0 <= seed <= MAX_SEED:
        raise BadRequest(f"seed fuori da 0..{MAX_SEED}: {seed}")
    return seed


def _parse_cases(raw: str | None) -> int:
    try:
        cases = int(raw or "")
    except ValueError as exc:
        raise BadRequest(f"numProcesses non e' un intero: {raw!r}") from exc
    if not 1 <= cases <= MAX_CASES:
        raise BadRequest(f"numProcesses fuori da 1..{MAX_CASES}: {cases}")
    return cases


def _stats_section_json(section: str) -> str:
    # Stessa conversione del microservizio upstream: la prima riga e' il titolo.
    return pandas.read_csv(StringIO(section), skiprows=1).to_json(orient="records")


def split_stats(contents: str) -> tuple[str, str, str]:
    """Le tre sezioni del CSV di statistiche, come JSON per record."""
    sections = contents.split('\n""\n')
    if len(sections) != 4:
        raise RuntimeError(f"statistiche Prosimos inattese: {len(sections)} sezioni invece di 4")
    _, resources, tasks, overall = sections
    return _stats_section_json(resources), _stats_section_json(tasks), _stats_section_json(overall)


def _purge_old_files(now: float | None = None) -> None:
    limit = (now or time.time()) - FILE_TTL_SECONDS
    for path in DATA_DIR.glob("*"):
        try:
            if path.stat().st_mtime >= limit:
                continue
            # Una cartella di lavoro rimasta qui e' di un run interrotto a meta'.
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink()
        except OSError:
            continue


def simulate(model: bytes, scenario: bytes, cases: int, start_date: str | None, seed: int) -> dict:
    """Un run di Prosimos con il seed dato; restituisce la risposta dell'API."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _purge_old_files()
    with tempfile.TemporaryDirectory(dir=DATA_DIR) as work:
        model_path = Path(work) / "model.bpmn"
        scenario_path = Path(work) / "scenario.json"
        model_path.write_bytes(model)
        scenario_path.write_bytes(scenario)
        stats_fd, stats_name = tempfile.mkstemp(prefix="stats_", suffix=".csv", dir=DATA_DIR)
        logs_fd, logs_name = tempfile.mkstemp(prefix="logs_", suffix=".csv", dir=DATA_DIR)
        os.close(stats_fd)
        os.close(logs_fd)
        _seed_everything(seed)
        run_simulation(
            str(model_path),
            str(scenario_path),
            total_cases=cases,
            stat_out_path=stats_name,
            log_out_path=logs_name,
            starting_at=start_date,
            is_event_added_to_log=False,
        )
    resources, tasks, overall = split_stats(Path(stats_name).read_text(encoding="utf-8"))
    return {
        # Doppia codifica come upstream: l'adapter la decodifica gia' cosi'.
        "ResourceUtilization": json.dumps(resources),
        "IndividualTaskStatistics": json.dumps(tasks),
        "OverallScenarioStatistics": json.dumps(overall),
        "StatsFilename": Path(stats_name).name,
        "LogsFilename": Path(logs_name).name,
        "Seed": seed,
        "EngineVersion": engine_version(),
    }


@app.post("/api/simulate")
def api_simulate():
    try:
        model = request.files.get("modelFile")
        scenario = request.files.get("simScenarioFile")
        if model is None or scenario is None:
            raise BadRequest("servono modelFile e simScenarioFile")
        cases = _parse_cases(request.form.get("numProcesses"))
        seed = _parse_seed(request.form.get("seed"))
        result = simulate(model.read(), scenario.read(), cases, request.form.get("startDate") or None, seed)
    except BadRequest as exc:
        return jsonify({"success": False, "errorMessage": str(exc)}), 400
    except _INPUT_ERRORS as exc:
        return jsonify({"success": False, "errorMessage": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001 - il chiamante deve leggere il motivo, non un 500 muto
        app.logger.exception("simulazione fallita")
        return jsonify({"success": False, "errorMessage": f"{type(exc).__name__}: {exc}"}), 500
    return jsonify(result)


@app.get("/api/simulationFile")
def api_simulation_file():
    name = request.args.get("fileName", "")
    if not _FILE_NAME.match(name):
        return jsonify({"success": False, "errorMessage": "fileName non valido"}), 400
    path = DATA_DIR / name
    if not path.is_file():
        return jsonify({"success": False, "errorMessage": "file non trovato o scaduto"}), 404
    return send_file(path, mimetype="text/csv", as_attachment=True, download_name=name)


@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "engine": "prosimos",
        "engineVersion": engine_version(),
        "python": sys.version.split()[0],
    })
