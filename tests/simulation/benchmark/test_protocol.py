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
LOCKS = [protocol.load_lock(path) for path in protocol.lock_paths()]  # PROTO-01 e il secondo set di PROTO-02

# Il codice che sviluppa e sceglie: benchmark, simulazione, event log e script.
SELECTION_ROOTS = ("tests/simulation", "backend/simulation", "backend/eventlog", "scripts")
# Gli unici file che possono nominare gli holdout: chi li congela, il lucchetto, questo test.
ALLOWED = {
    "tests/simulation/benchmark/protocol_freeze.py",
    "tests/simulation/benchmark/protocol/holdout.lock.json",
    "tests/simulation/benchmark/protocol/holdout2.lock.json",
    "tests/simulation/benchmark/test_protocol.py",
}
SCANNED_SUFFIXES = (".py", ".sh", ".yml", ".yaml", ".toml", ".json", ".md", ".txt", ".cfg", ".ini")


def _tracked_files(*roots: str) -> list[str]:
    out = subprocess.run(["git", "ls-files", *roots], cwd=protocol.ROOT, capture_output=True, text=True, check=True)
    return out.stdout.split()


def _holdout_patterns() -> list[re.Pattern[str]]:
    names = sorted(set().union(*(protocol.blocked_names(path).names for path in protocol.lock_paths())))
    patterns = [re.compile(re.escape(name), re.IGNORECASE) for name in names]
    for holdout in (h for lock in LOCKS for h in lock["holdouts"]):
        for stem in holdout["names"]:
            # il nome del log con un'estensione da log, o fra virgolette (un id costruito a mano)
            suffixes = "|".join(re.escape(s) for s in protocol.LOG_SUFFIXES)
            patterns.append(re.compile(rf"(?<![\w]){re.escape(stem)}(?:{suffixes})\b", re.IGNORECASE))
            patterns.append(re.compile(rf"[\"']{re.escape(stem)}(?:_(?:train|test))?[\"']"))
    closed = sorted({h["dataset"] for lock in LOCKS for h in lock["holdouts"] if h.get("closes_dataset", True)})
    patterns += [re.compile(rf"[\"']{re.escape(dataset)}[\"']") for dataset in closed]
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


def _props(train: list[Event], test: list[Event], start: float = 1.0, resource: float = 1.0) -> protocol.LogProperties:
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
    assert props.censored_right_test == 0.0
    assert protocol.identifiability(props, synthetic=False)["cycle_time_w1"][0] == protocol.IDENTIFIABLE


def test_a_test_period_with_a_different_arrival_flow_does_not_validate_arrivals():
    """Come BPIC 2013 incidents (arrivi di B 200 volte quelli di A): CAR non validato."""
    train = _log(100)
    burst = [Event(e.case_id, e.activity, T0 + timedelta(days=60, minutes=(e.start - T0).total_seconds() / 3600), e.end)
             for e in _log(100, start=100)]
    burst = [Event(e.case_id, e.activity, e.start, e.start + timedelta(minutes=10)) for e in burst]
    verdict, why = protocol.identifiability(_props(train, burst), synthetic=False)["case_arrival"]
    assert verdict == protocol.NOT_VALIDATED and "non sono lo stesso flusso" in why


# --------------------------------------------------------------------------- casi trovati in review


@pytest.mark.parametrize(
    "relative",
    [
        "camargo-2022-reproducibility/reproducibility_package_caise_22/experiment_1/data/generated_logs/MP/SIMOD/Production_1.csv",
        "reproducibility_package_caise_22/experiment_2/scenario_2/models/CFM/modified/bpmn_models/confidential_2000_modif.bpmn",
        "camargo-2022-reproducibility/qualsiasi_nome.txt",
        "bpic2015-municipality1/BPIC15_1.xes.part",
    ],
)
def test_files_derived_from_holdouts_or_inside_their_datasets_are_closed(tmp_path: Path, relative: str):
    """Log simulati da modelli addestrati sugli holdout, il modello vero modificato, tutto il pacchetto."""
    planted = tmp_path / relative
    planted.parent.mkdir(parents=True)
    planted.write_bytes(b"x")
    with protocol.selection_phase(), pytest.raises(protocol.HoldoutAccessError):
        planted.read_bytes()


def test_a_hard_link_with_an_innocent_name_is_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    holdout = _plant(tmp_path, HOLDOUT_FILES[0])
    link = tmp_path / "copia.bin"
    os.link(holdout, link)
    stat = holdout.stat()
    monkeypatch.setattr(protocol, "_frozen_files", {(stat.st_dev, stat.st_ino)})
    with protocol.selection_phase(), pytest.raises(protocol.HoldoutAccessError):
        link.read_bytes()


def test_opening_holdouts_in_one_thread_keeps_them_closed_in_the_others(tmp_path: Path):
    import threading

    planted = _plant(tmp_path, HOLDOUT_FILES[0])
    inside, release, seen = threading.Event(), threading.Event(), []

    def final() -> None:
        with protocol.final_evaluation(protocol.lock_digest()):
            inside.set()
            release.wait(5)

    def selection() -> None:
        try:
            with protocol.selection_phase():
                planted.read_bytes()
            seen.append("letto")
        except protocol.HoldoutAccessError:
            seen.append("chiuso")

    opener = threading.Thread(target=final)
    opener.start()
    inside.wait(5)
    reader = threading.Thread(target=selection)
    reader.start()
    reader.join(5)
    release.set()
    opener.join(5)
    assert seen == ["chiuso"]
    with pytest.raises(protocol.HoldoutAccessError):
        planted.read_bytes()  # il thread principale non e' mai stato aperto


def test_generic_configuration_files_are_not_blocked(tmp_path: Path):
    for name in ("production.json", "production.xml", "Production.yaml"):
        planted = _plant(tmp_path, name)
        with protocol.selection_phase():
            assert planted.read_bytes()


def test_every_development_log_is_listed_none_missing():
    logs = protocol.development_logs()
    assert len(logs) == 25
    assert sum(log.category == protocol.SYNTHETIC for log in logs) == 20
    for log in logs:
        if log.source.startswith("datasets/"):
            assert list(protocol.ROOT.glob(log.source.replace("{train,test}", "*"))), log.source


# --------------------------------------------------------------------------- PROTO-02: confronti appaiati


def test_paired_comparison_finds_a_consistent_small_improvement_that_intervals_miss():
    """Repliche appaiate: a e' sempre un po' meglio di b. Gli IC si sovrappongono, il test appaiato no."""
    base = [10.0, 14.0, 9.0, 16.0, 11.0, 13.0, 8.0, 15.0, 12.0, 10.5]
    better = [v - 0.5 for v in base]
    from tests.simulation.benchmark.eval_harness import summarize, within_intervals

    assert within_intervals(summarize(better), summarize(base))  # per la regola degli IC: pari
    result = protocol.paired_comparison(better, base)
    assert result.verdict == "a meglio"
    assert result.mean_difference == pytest.approx(-0.5)
    assert result.ci_high < 0 and result.wilcoxon_p < protocol.PAIRED_ALPHA


def test_paired_comparison_is_even_on_noise_and_symmetric():
    a = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    b = [1.2, 1.8, 3.1, 3.9, 5.2, 5.8, 7.1, 7.9, 9.0, 10.0]
    assert protocol.paired_comparison(a, b).verdict == "pari"
    forward, backward = protocol.paired_comparison(a, b), protocol.paired_comparison(b, a)
    assert forward.mean_difference == pytest.approx(-backward.mean_difference)
    assert forward.wilcoxon_p == backward.wilcoxon_p


def test_paired_comparison_is_deterministic_and_needs_pairs():
    a, b = [3.0, 4.0, 5.0], [3.5, 4.4, 5.1]
    assert protocol.paired_comparison(a, b) == protocol.paired_comparison(a, b)
    with pytest.raises(ValueError):
        protocol.paired_comparison([1.0, 2.0], [1.0])


def test_wilcoxon_p_matches_the_table():
    # n = 10, un solo segno negativo sul rango 2: W+ = 53, p = 6/1024 (tavola esatta a due code).
    assert protocol._wilcoxon_p([1, -2, 3, 4, 5, 6, 7, 8, 9, 10]) == pytest.approx(6 / 1024)
    assert protocol._wilcoxon_p([0.0, 0.0]) == 1.0


# --------------------------------------------------------------------------- PROTO-02: metriche di CF-01


def _outcome(true_delta, predicted, low, high, baseline=100.0):
    return protocol.CounterfactualOutcome(baseline, true_delta, predicted, low, high)


def test_counterfactual_metrics_report_width_error_and_direction_not_only_coverage():
    wide = [_outcome(-10, 5, -500, 500), _outcome(8, -3, -500, 500)]
    narrow = [_outcome(-10, -9, -12, -7), _outcome(8, 7, 5, 10)]
    w, n = protocol.counterfactual_metrics(wide), protocol.counterfactual_metrics(narrow)
    assert w.coverage == n.coverage == 1.0  # la copertura da sola non li distingue
    assert w.mean_width == 1000 and n.mean_width == 5
    assert w.direction_accuracy == 0.0 and n.direction_accuracy == 1.0
    assert w.mean_absolute_error == 13 and n.mean_absolute_error == 1
    assert n.mean_relative_error == pytest.approx(0.01)


def test_counterfactual_direction_ignores_effects_too_small_to_have_one():
    tiny = _outcome(0.5, -0.4, -1, 1)  # 0,5% del KPI: sotto DIRECTION_MIN_EFFECT
    metrics = protocol.counterfactual_metrics([tiny])
    assert metrics.direction_cases == 0 and metrics.direction_accuracy is None
    assert metrics.coverage == 1.0


def test_counterfactual_metrics_reject_bad_input():
    with pytest.raises(ValueError):
        protocol.counterfactual_metrics([])
    with pytest.raises(ValueError):
        protocol.counterfactual_metrics([_outcome(1, 1, 2, 0)])
    with pytest.raises(ValueError):
        protocol.counterfactual_metrics([_outcome(1, 1, 0, 2, baseline=0)])


# --------------------------------------------------------------------------- PROTO-02: due set di holdout


def _second_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, closes_dataset: bool) -> Path:
    """Un secondo lucchetto di prova accanto al primo, vero e invariato."""
    lock = tmp_path / "holdout2.lock.json"
    lock.write_text(json.dumps({
        "protocol": "prova",
        "holdouts": [{
            "id": "secondo", "dataset": "pacchetto-misto", "closes_dataset": closes_dataset,
            "names": ["SecondoSet"],
            "files": [{"path": "logs/SecondoSet.csv.gz", "sha256": "0" * 64, "bytes": 1}],
        }],
    }), encoding="utf-8")
    monkeypatch.setattr(protocol, "lock_paths", lambda: (protocol.LOCK_PATH, lock))
    return lock


def test_the_second_lock_closes_its_logs_and_derived_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _second_lock(tmp_path, monkeypatch, closes_dataset=False)
    assert protocol.is_holdout("cache/altro/SecondoSet.csv.gz")
    assert protocol.is_holdout("cache/altro/secondoset_simulato_3.csv")
    assert not protocol.is_holdout("cache/pacchetto-misto/logs/sviluppo.csv.gz")  # il pacchetto resta di sviluppo
    planted = _plant(tmp_path, "SecondoSet.csv")
    with protocol.selection_phase(), pytest.raises(protocol.HoldoutAccessError):
        planted.read_bytes()


def test_a_second_lock_can_close_the_whole_dataset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _second_lock(tmp_path, monkeypatch, closes_dataset=True)
    assert protocol.is_holdout("cache/pacchetto-misto/logs/sviluppo.csv.gz")


def test_final_evaluation_opens_one_set_and_keeps_the_other_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    second = _second_lock(tmp_path, monkeypatch, closes_dataset=False)
    first_log = _plant(tmp_path, HOLDOUT_FILES[0])
    second_log = _plant(tmp_path, "SecondoSet.csv")
    with protocol.final_evaluation(protocol.lock_digest()):
        assert first_log.read_bytes()
        with pytest.raises(protocol.HoldoutAccessError):
            second_log.read_bytes()
    with protocol.final_evaluation(protocol.lock_digest(second)):
        assert second_log.read_bytes()
        with pytest.raises(protocol.HoldoutAccessError):
            first_log.read_bytes()
    with protocol.selection_phase(), pytest.raises(protocol.HoldoutAccessError):
        second_log.read_bytes()


def test_the_second_lock_digest_is_written_in_the_protocol():
    assert protocol.LOCK2_PATH in protocol.lock_paths(), "secondo set non congelato"
    assert protocol.lock_digest(protocol.LOCK2_PATH) in protocol.PROTOCOL_DOC.read_text(encoding="utf-8")


def test_the_second_set_is_independent_of_the_first_and_of_development():
    first, second = (protocol.load_lock(path) for path in (protocol.LOCK_PATH, protocol.LOCK2_PATH))
    assert second["independent_of"].endswith(protocol.lock_digest(protocol.LOCK_PATH))
    hashes = lambda lock: {f["sha256"] for h in lock["holdouts"] for f in h["files"]}  # noqa: E731
    assert not hashes(first) & hashes(second)
    assert not {h["id"] for h in first["holdouts"]} & {h["id"] for h in second["holdouts"]}
    for log in protocol.development_logs():
        assert not protocol.is_holdout(log.source, [protocol.LOCK2_PATH]), log.source
    assert {h["category"] for h in second["holdouts"]} == {protocol.COMPLETE, protocol.PARTIAL}


def test_frozen_second_set_in_the_cache_matches_the_lock():
    root = fetch_datasets.cache_dir()
    datasets = sorted({h["dataset"] for h in protocol.load_lock(protocol.LOCK2_PATH)["holdouts"]})
    if not all((root / d).is_dir() for d in datasets):
        pytest.skip("secondo set non scaricato: scripts/fetch_datasets.py fetch " + " ".join(datasets))
    assert protocol.verify_frozen(root, protocol.LOCK2_PATH) == []


def test_every_radar_entry_has_a_declared_role():
    """PROTO-02: ogni voce del radar ha un ruolo (sviluppo, holdout 2, escluso, codice) e un motivo."""
    text = protocol.PROTOCOL_DOC.read_text(encoding="utf-8")
    section = text[text.index("### Ruolo di ogni voce"):text.index("### Secondo set di holdout")]
    roles: dict[str, str] = {}
    for line in section.splitlines():
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) == 3 and cells[0].startswith("`"):
            for ident in re.findall(r"`([^`]+)`", cells[0]):
                roles[ident] = cells[1]
            assert cells[2], f"{cells[0]}: manca il motivo"
    radar = {i for i, e in fetch_datasets.load_manifest().items() if e.get("collection") == "radar"}
    assert set(roles) == radar
    assert all(re.match(r"(sviluppo|holdout 2|escluso|codice)", role) for role in roles.values()), roles
    second = {h["dataset"] for h in protocol.load_lock(protocol.LOCK2_PATH)["holdouts"]}
    assert all("holdout 2" in roles[dataset] for dataset in second)


def test_paired_comparison_accepts_all_the_replicas_the_harness_allows():
    a = [float(i) for i in range(31)]
    b = [v + 1 + (i % 3) * 0.1 for i, v in enumerate(a)]
    result = protocol.paired_comparison(a, b)
    assert result.verdict == "a meglio" and result.wilcoxon_p < 1e-5  # approssimazione normale oltre 20
