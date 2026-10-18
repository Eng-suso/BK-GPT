"""Runner Prosimos di DeliR: Prosimos 2.x dietro la stessa API che l'adapter usa oggi.

Sostituisce il microservizio upstream patchato (Prosimos 1.2.6, Python 3.9):
vedi docs/simulation-prosimos-2x-spike.md per il perche'.

API, compatibile con ``backend/simulation/prosimos_adapter.py``:

- ``POST /api/simulate`` (multipart): ``modelFile``, ``simScenarioFile``,
  ``numProcesses``, ``startDate`` e, in piu', ``seed`` opzionale. Risponde con
  ``ResourceUtilization``, ``IndividualTaskStatistics``,
  ``OverallScenarioStatistics`` (stringhe JSON, come upstream), ``StatsFilename``,
  ``LogsFilename``, e ``Seed`` / ``EngineVersion`` / ``ArrivalBands``. Se lo
  scenario porta ``delir_arrival_bands``, gli arrivi li genera il runner per
  fascia oraria (``arrival_bands.py``).
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

import csv
import json
import os
import random
import re
import secrets
import shutil
import sys
import tempfile
import time
from datetime import datetime
from importlib.metadata import version
from io import StringIO
from pathlib import Path

import numpy
import pandas
import pytz
from flask import Flask, jsonify, request, send_file
from prosimos.exceptions import (
    InvalidBpmnModelException,
    InvalidLogFileException,
    InvalidSimScenarioException,
)
from prosimos.simulation_engine import SimBPMEnv, execute_full_process, run_simulation
from prosimos.simulation_properties_parser import parse_datetime
from prosimos.simulation_setup import SimDiffSetup

from arrival_bands import ATTRIBUTE_SECTION, SECTION, arrival_plan, band_label, weekly_intervals

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
        bands = _arrival_bands(scenario)
        if bands is None:
            run_simulation(
                str(model_path),
                str(scenario_path),
                total_cases=cases,
                stat_out_path=stats_name,
                log_out_path=logs_name,
                starting_at=start_date,
                is_event_added_to_log=False,
            )
        else:
            _simulate_with_arrivals(model_path, scenario_path, cases, start_date, bands, _band_attribute(scenario),
                                    stats_name, logs_name)
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
        # Quante fasce degli arrivi il runner ha applicato: l'adapter rifiuta un
        # motore che le ignorerebbe in silenzio.
        "ArrivalBands": 0 if bands is None else len(bands),
    }


def _simulate_with_arrivals(model_path: Path, scenario_path: Path, cases: int, start_date: str | None,
                            bands: list[dict], band_attribute: str | None, stats_name: str, logs_name: str) -> None:
    """``run_simulation`` con gli arrivi calcolati dal runner per fascia oraria.

    Con ``fixed_arrival_times`` Prosimos 2.1 esegue il processo ma torna prima
    di scrivere log e statistiche (``run_simpy_simulation``): qui si ripetono
    gli stessi passi di ``run_simulation`` e ``run_simpy_simulation``, scrittura
    compresa.
    """
    setup = SimDiffSetup(str(model_path), str(scenario_path), False, cases)
    start = parse_datetime(start_date, True) if start_date else pytz.utc.localize(datetime.now())
    setup.set_starting_datetime(start)
    arrivals, indices = arrival_plan(bands, start, cases)
    writer = {"delimiter": ",", "quotechar": '"', "quoting": csv.QUOTE_MINIMAL}
    with open(stats_name, "w", newline="", encoding="utf-8") as stats, \
            open(logs_name, "w", newline="", encoding="utf-8") as logs:
        env = SimBPMEnv(setup, csv.writer(stats, **writer), csv.writer(logs, **writer))
        if band_attribute:
            _label_cases(env, band_attribute, indices)
        execute_full_process(env, arrivals)
        env.log_writer.force_write()
        env.log_info.save_joint_statistics(env)


def _label_cases(env: SimBPMEnv, attribute: str, indices: list[int]) -> None:
    """SIM-33: ogni caso riceve nell'attributo la fascia in cui arriva, poi la sua priorita'.

    Prosimos estrae gli attributi di tutti i casi alla creazione dell'ambiente
    (``CasePrioritisation``) e li condivide con regole, durate e log: si riscrive
    il valore li', prima che parta il primo caso. La priorita' dipende dagli
    attributi, quindi si ricalcola.
    """
    prioritisation = env.case_prioritisation
    for case_id, index in enumerate(indices):
        attributes = prioritisation.all_case_attributes[case_id]
        if attribute not in attributes:
            raise BadRequest(f"{ATTRIBUTE_SECTION}: l'attributo {attribute!r} non e' fra gli attributi del caso")
        attributes[attribute] = band_label(index)
        prioritisation.all_case_priorities[case_id] = prioritisation.prioritisation_rules.get_priority(attributes)


def _band_attribute(scenario: bytes) -> str | None:
    value = json.loads(scenario).get(ATTRIBUTE_SECTION)
    if value is not None and (not isinstance(value, str) or not value):
        raise BadRequest(f"{ATTRIBUTE_SECTION} non valido: serve il nome di un attributo del caso")
    return value


def _arrival_bands(scenario: bytes) -> list[dict] | None:
    try:
        payload = json.loads(scenario)
    except ValueError:
        return None  # lo scenario non valido lo segnala Prosimos, con il suo messaggio
    bands = payload.get(SECTION) if isinstance(payload, dict) else None
    if bands is None:
        return None
    try:
        weekly_intervals(bands)
    except (ValueError, KeyError, TypeError) as exc:
        raise BadRequest(f"{SECTION} non valido: {exc}") from exc
    return bands


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
