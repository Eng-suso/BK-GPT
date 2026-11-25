"""PROTO-01: gli holdout restano chiusi al codice di selezione, le regole valgono per ogni log.

Il test principale (``test_selection_code_*``) fallisce se il codice di selezione
legge un log holdout o lo nomina. Senza rete: i log holdout non servono, la
guardia si prova su file che ne portano il nome.
"""

from __future__ import annotations

import gzip
import json
import os
import re
import shutil
import subprocess
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts import fetch_datasets
from tests.simulation.benchmark import protocol
from tests.simulation.benchmark.log_distance import Event, read_csv_log

LOCK = protocol.load_lock()
HOLDOUT_FILES = sorted({Path(f["path"]).name for h in LOCK["holdouts"] for f in h["files"]})
HOLDOUT_DATASETS = sorted({h["dataset"] for h in LOCK["holdouts"]})

# Il codice che sviluppa e sceglie: benchmark, simulazione, event log e script.
SELECTION_ROOTS = ("tests/simulation", "backend/simulation", "backend/eventlog", "scripts")
# Gli unici file che possono nominare gli holdout: chi li congela, il lucchetto, questo test.
ALLOWED = {
    "tests/simulation/benchmark/protocol_freeze.py",
    "tests/simulation/benchmark/protocol/holdout.lock.json",
    "tests/simulation/benchmark/test_protocol.py",
}
SCANNED_SUFFIXES = (".py", ".sh", ".yml", ".yaml", ".toml", ".json", ".md", ".txt", ".cfg", ".ini")


def _tracked_files(*roots: str) -> list[str]:
    out = subprocess.run(["git", "ls-files", *roots], cwd=protocol.ROOT, capture_output=True, text=True, check=True)
    return out.stdout.split()


def _holdout_patterns() -> list[re.Pattern[str]]:
    blocked = protocol.blocked_names()
    patterns = [re.compile(re.escape(name), re.IGNORECASE) for name in sorted(blocked.names)]
    for holdout in LOCK["holdouts"]:
        for stem in holdout["names"]:
            # il nome del log con un'estensione da log, o fra virgolette (un id costruito a mano)
            suffixes = "|".join(re.escape(s) for s in protocol.LOG_SUFFIXES)
            patterns.append(re.compile(rf"(?<![\w]){re.escape(stem)}(?:{suffixes})\b", re.IGNORECASE))
            patterns.append(re.compile(rf"[\"']{re.escape(stem)}(?:_(?:train|test))?[\"']"))
    patterns += [re.compile(rf"[\"']{re.escape(dataset)}[\"']") for dataset in HOLDOUT_DATASETS]
    return patterns


# --------------------------------------------------------------------------- il test della meta


def test_selection_code_does_not_name_a_holdout_log():
    """Nessun file del codice di selezione nomina un log holdout o il suo dataset."""
    patterns = _holdout_patterns()
    offenders = []
    for relative in _tracked_files(*SELECTION_ROOTS):
        if relative in ALLOWED or not relative.endswith(SCANNED_SUFFIXES):
            continue
        text = (protocol.ROOT / relative).read_text(encoding="utf-8", errors="ignore")
        offenders += [f"{relative}: {m.group(0)}" for p in patterns for m in [p.search(text)] if m]
    assert not offenders, "codice di selezione che nomina log holdout:\n" + "\n".join(offenders)


def _plant(tmp_path: Path, name: str, payload: bytes = b"case_id,activity,start_time,end_time\n") -> Path:
    path = tmp_path / name
    path.write_bytes(payload)
    return path


def _fake_selection(path: Path, how: str) -> None:
    """Un pezzo di codice di selezione che prova a leggere un file in uno dei modi comuni."""
    if how == "open":
        with open(path, "rb") as handle:
            handle.read()
    elif how == "pathlib":
        path.read_bytes()
    elif how == "gzip":
        with gzip.open(path) as handle:
            handle.read()
    elif how == "zipfile":
        zipfile.ZipFile(path)
    elif how == "os.open":
        os.close(os.open(path, os.O_RDONLY))
    elif how == "copy":
        shutil.copy(path, path.with_name("innocuo.bin"))
    elif how == "read_csv_log":
        read_csv_log(path)


@pytest.mark.parametrize("how", ["open", "pathlib", "gzip", "zipfile", "os.open", "copy", "read_csv_log"])
@pytest.mark.parametrize("name", HOLDOUT_FILES)
def test_selection_code_reading_a_holdout_fails(tmp_path: Path, name: str, how: str):
    planted = _plant(tmp_path, name)
    with protocol.selection_phase(), pytest.raises(protocol.HoldoutAccessError):
        _fake_selection(planted, how)


@pytest.mark.parametrize("name", ["production.parquet", "BPIC15_1.csv.gz", "tst_Production.csv", "Hospital_log.xes"])
def test_a_converted_or_renamed_copy_is_still_closed(tmp_path: Path, name: str):
    planted = _plant(tmp_path, name)
    with protocol.selection_phase(), pytest.raises(protocol.HoldoutAccessError):
        planted.read_bytes()


def test_a_symlink_with_an_innocent_name_is_still_closed(tmp_path: Path):
    target = _plant(tmp_path, HOLDOUT_FILES[0])
    link = tmp_path / "log_qualsiasi.csv"
    link.symlink_to(target)
    with protocol.selection_phase(), pytest.raises(protocol.HoldoutAccessError):
        link.read_bytes()


def test_the_archive_that_contains_holdouts_is_closed(tmp_path: Path):
    planted = _plant(tmp_path, LOCK["containers"][0]["file"])
    with protocol.selection_phase(), pytest.raises(protocol.HoldoutAccessError):
        planted.read_bytes()


def test_selection_code_reads_every_development_log():
    """Nessun falso allarme: i log di sviluppo nel repo si leggono dentro la fase di selezione."""
    with protocol.selection_phase():
        for log in protocol.development_logs():
            if log.source.startswith("datasets/"):
                for path in protocol.ROOT.glob(log.source.replace("{train,test}", "*")):
                    assert read_csv_log(path), path


def test_selection_modules_import_without_touching_holdouts():
    """Importare ogni modulo del benchmark (anche quelli che leggono file all'import) e' sicuro."""
    import importlib

    modules = [
        p.relative_to(protocol.ROOT).with_suffix("").as_posix().replace("/", ".")
        for p in protocol.BENCHMARK.rglob("*.py")
        if not p.name.startswith("test_") and p.name != "protocol_freeze.py"
    ]
    imported = 0
    with protocol.selection_phase():
        for module in modules:
            try:
                importlib.import_module(module)
            except ModuleNotFoundError:  # libreria del solo venv di riferimento (log_distance_reference)
                continue
            except RuntimeError as exc:  # serve lo stack reale (database): fuori da questo test
                assert "non configurata" in str(exc), exc
                continue
            imported += 1
    assert imported >= len(modules) // 2


# --------------------------------------------------------------------------- lucchetto


def test_the_lock_digest_is_written_in_the_protocol():
    """Cambiare un holdout cambia l'impronta, e l'impronta e' scritta in PROTOCOL.md."""
    assert protocol.lock_digest() in protocol.PROTOCOL_DOC.read_text(encoding="utf-8")


def test_holdouts_are_frozen_with_hash_size_and_reason():
    sha256 = re.compile(r"^[0-9a-f]{64}$")
    manifest = fetch_datasets.load_manifest()
    for holdout in LOCK["holdouts"]:
        assert holdout["category"] in {protocol.COMPLETE, protocol.PARTIAL, protocol.SYNTHETIC}, holdout["id"]
        assert holdout["independent_because"] and holdout["split"], holdout["id"]
        assert manifest[holdout["dataset"]]["mode"] == "fetch", "un holdout non sta nel repo"
        for item in holdout["files"]:
            assert sha256.match(item["sha256"]) and item["bytes"] > 0, item["path"]


def test_holdouts_cover_the_three_categories():
    assert {h["category"] for h in LOCK["holdouts"]} == {protocol.COMPLETE, protocol.PARTIAL, protocol.SYNTHETIC}


def test_no_holdout_file_is_in_the_repository():
    """Il repo e' pubblico e gli holdout non si leggono: nessuna loro copia nei file tracciati."""
    tracked = [p for p in _tracked_files() if p not in ALLOWED]
    assert not [p for p in tracked if protocol.is_holdout(p)]


def test_holdouts_and_development_logs_are_disjoint():
    stems = protocol.blocked_names().stems
    for log in protocol.development_logs():
        assert log.key.lower() not in stems, log.key
        assert not protocol.is_holdout(log.source), log.source


def test_frozen_holdouts_in_the_cache_match_the_lock():
    root = fetch_datasets.cache_dir()
    if not all((root / dataset).is_dir() for dataset in HOLDOUT_DATASETS):
        pytest.skip("holdout non scaricati: scripts/fetch_datasets.py fetch " + " ".join(HOLDOUT_DATASETS))
    assert protocol.verify_frozen(root) == []


def test_final_evaluation_needs_the_lock_digest(tmp_path: Path):
    planted = _plant(tmp_path, HOLDOUT_FILES[0])
    with pytest.raises(protocol.HoldoutAccessError):
        with protocol.final_evaluation("0" * 64):
            pass
    with protocol.final_evaluation(protocol.lock_digest()):
        assert planted.read_bytes()
    with protocol.selection_phase(), pytest.raises(protocol.HoldoutAccessError):
        planted.read_bytes()  # chiusi di nuovo all'uscita


def test_the_lock_is_valid_json_and_frozen_before_any_measure():
    assert LOCK["frozen_on"] <= "2026-11-25"
    json.dumps(LOCK)


# --------------------------------------------------------------------------- divisioni

T0 = datetime(2026, 1, 5, 9, tzinfo=UTC)


def _log(n: int, *, activities: tuple[str, ...] = ("Ricevi", "Valuta", "Chiudi"), start: int = 0) -> list[Event]:
    events = []
    for i in range(start, start + n):
        t = T0 + timedelta(hours=6 * i)
        for k, activity in enumerate(activities):
            events.append(Event(f"c{i:04d}", activity, t + timedelta(hours=k), t + timedelta(hours=k, minutes=30)))
    return events


def test_validation_is_the_last_fifth_of_the_train_by_case_start():
    train = _log(100)
    fit, validation = protocol.train_validation(train)
    fit_cases = {e.case_id for e in fit}
    validation_cases = {e.case_id for e in validation}
    assert len(fit_cases) == 80 and len(validation_cases) == 20
    assert not fit_cases & validation_cases
    assert max(fit_cases) < min(validation_cases)  # tutto il fit viene prima
    assert protocol.train_validation(list(reversed(train))) == (
        [e for e in reversed(train) if e.case_id in fit_cases],
        [e for e in reversed(train) if e.case_id in validation_cases],
    )


def test_a_split_never_cuts_a_case_and_rejects_bad_fractions():
    with pytest.raises(ValueError):
        protocol.split_by_start(_log(10), 1.0)
    with pytest.raises(ValueError):
        protocol.split_by_start(_log(1), 0.5)
    first, last = protocol.split_by_start(_log(3), 0.5)
    assert {e.case_id for e in first}.isdisjoint({e.case_id for e in last})


# --------------------------------------------------------------------------- identificabilita'


def _props(train: list[Event], test: list[Event], start: float = 1.0, resource: float = 1.0) -> dict:
    n = len(train) + len(test)
    return protocol.properties(
        train, test, has_start=[i < start * n for i in range(n)], has_resource=[i < resource * n for i in range(n)]
    )


def test_a_complete_log_validates_every_observable_metric():
    verdicts = protocol.identifiability(_props(_log(100), _log(100, start=100)), synthetic=False)
    for metric in ("cycle_time_w1", "ngram", "relative_event", "absolute_event", "circadian_event", "case_arrival", "processing_time", "resources"):
        assert verdicts[metric][0] == protocol.IDENTIFIABLE, metric
    for metric in ("waiting_causes", "true_parameters", "counterfactual"):
        assert verdicts[metric] == (protocol.NOT_VALIDATED, "serve la verita' del processo: c'e' solo nei sintetici")


def test_a_snapshot_log_is_not_validated_on_case_durations_but_stays():
    """Come BPIC 2013 incidents: i casi di B tagliati dalla fine e iniziati prima del log."""
    test = _log(100, start=100, activities=("Valuta",))  # ne' inizio ne' fine osservati
    verdicts = protocol.identifiability(_props(_log(100), test, start=0.0), synthetic=False)
    for metric in ("cycle_time_w1", "ngram", "relative_event", "case_arrival", "processing_time"):
        assert verdicts[metric][0] == protocol.NOT_VALIDATED, metric
    assert "100% dei casi di test tagliati" in verdicts["cycle_time_w1"][1]
    assert verdicts["absolute_event"][0] == verdicts["circadian_event"][0] == protocol.IDENTIFIABLE


def test_a_synthetic_log_validates_the_truth_and_the_counterfactual():
    verdicts = protocol.identifiability(_props(_log(100), _log(100, start=100)), synthetic=True)
    assert all(v[0] == protocol.IDENTIFIABLE for v in verdicts.values())


def test_too_few_cases_validate_nothing():
    verdicts = protocol.identifiability(_props(_log(20), _log(20, start=20)), synthetic=True)
    assert all(v[0] == protocol.NOT_VALIDATED for v in verdicts.values())


def test_rare_end_activities_are_not_counted_as_cut_cases():
    """Un log completo con il 6% di casi che finiscono in un'attivita' rara: nessun taglio."""
    def rare(n: int, start: int) -> list[Event]:
        out = []
        for e in _log(n, start=start):
            rare_case = int(e.case_id[1:]) % 16 == 0  # ~6% dei casi
            out.append(Event(e.case_id, "Archivia", e.start, e.end) if rare_case and e.activity == "Chiudi" else e)
        return out

    props = _props(rare(200, 0), rare(200, 200))
    assert props["censored_right_test"] == 0.0
    assert protocol.identifiability(props, synthetic=False)["cycle_time_w1"][0] == protocol.IDENTIFIABLE


def test_a_test_period_with_a_different_arrival_flow_does_not_validate_arrivals():
    """Come BPIC 2013 incidents (arrivi di B 200 volte quelli di A): CAR non validato."""
    train = _log(100)
    burst = [Event(e.case_id, e.activity, T0 + timedelta(days=60, minutes=(e.start - T0).total_seconds() / 3600), e.end)
             for e in _log(100, start=100)]
    burst = [Event(e.case_id, e.activity, e.start, e.start + timedelta(minutes=10)) for e in burst]
    verdict, why = protocol.identifiability(_props(train, burst), synthetic=False)["case_arrival"]
    assert verdict == protocol.NOT_VALIDATED and "non sono lo stesso flusso" in why
