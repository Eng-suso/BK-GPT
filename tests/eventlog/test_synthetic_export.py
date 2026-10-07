"""Il log di una simulazione diventa un event log canonico che si esporta e si rilegge uguale."""

from pathlib import Path

import pytest

from backend.eventlog.export import to_csv, to_xes
from backend.eventlog.kpi import summarize, timing
from backend.eventlog.mapping import ColumnMapping, apply_mapping
from backend.eventlog.readers import read_csv, read_xes
from backend.eventlog.synthetic import from_prosimos_csv
from backend.simulation.log_processor import ProsimosLogError

SAMPLE = (Path(__file__).resolve().parents[1] / "fixtures" / "prosimos" / "sim_log_sample.csv").read_text(
    encoding="utf-8"
)

CSV_MAPPING = ColumnMapping(
    case_id=("case_id",), activity=("activity",), start="start_time", end="end_time", resource="resource", role="role"
)


def _kpis(log):
    summary = summarize(log)
    return {key: summary[key] for key in ("cases", "events", "cycleTime", "waitingTime", "processingTime") if key in summary}


def test_the_prosimos_log_becomes_a_simulated_canonical_log():
    log = from_prosimos_csv(SAMPLE)

    assert log.origin == "simulated"
    assert len(log.events) == len(SAMPLE.strip().splitlines()) - 1
    assert timing(log) == "start_and_end"
    first = log.cases()["0"][0]
    assert first.activity == "Ricevi richiesta"
    assert first.resource == "Operatore_0" and first.role == "Operatore"


def test_an_unreadable_prosimos_log_is_refused():
    with pytest.raises(ProsimosLogError):
        from_prosimos_csv("a,b\n1,2\n")


def test_csv_export_is_reimported_with_the_same_kpis():
    original = from_prosimos_csv(SAMPLE)

    exported = to_csv(original)
    reimported = apply_mapping(read_csv(exported.content), CSV_MAPPING, source_name="run.csv")[0]

    assert len(reimported.events) == len(original.events)
    assert _kpis(reimported) == _kpis(original)


def test_xes_export_is_reimported_with_the_same_kpis():
    original = from_prosimos_csv(SAMPLE)

    exported = to_xes(original, metadata={"deliR:seed": 42})
    table = read_xes(exported.content)
    mapping = ColumnMapping(
        case_id=("case:concept:name",),
        activity=("concept:name",),
        timestamp="time:timestamp",
        lifecycle="lifecycle:transition",
        resource="org:resource",
        role="org:role",
    )
    reimported = apply_mapping(table, mapping, source_name="run.xes")[0]

    assert len(reimported.events) == len(original.events)
    assert _kpis(reimported) == _kpis(original)


def test_the_same_log_always_exports_the_same_bytes():
    log = from_prosimos_csv(SAMPLE)

    assert to_csv(log).sha256 == to_csv(log).sha256
    assert to_xes(log).sha256 == to_xes(log).sha256
    assert to_csv(log).sha256 != to_xes(log).sha256


def test_xes_escapes_names_with_markup():
    log = from_prosimos_csv(SAMPLE.replace("Revisione", 'Rivedi <"A&B">'))

    xes = to_xes(log).content.decode("utf-8")

    assert "&lt;" in xes and "<\"A&B\">" not in xes
    read_xes(xes.encode("utf-8"))
