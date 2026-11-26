"""RAD-01: l'inventario del radar legge i log, riconosce le copie e non apre gli holdout.

Senza rete e senza la cache: i log sono piccoli file scritti qui.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import zipfile
from pathlib import Path

import pytest

from tests.simulation.benchmark import protocol
from tests.simulation.benchmark import radar_inventory as inv

ORIGIN = inv.Origin("reale", "prova", "prova")
CSV = (
    "case_id,activity,start_time,end_time,resource\n"
    "c10001,Register,2024-01-01T08:00:00,2024-01-01T08:10:00,ann\n"
    "c10001,Check,2024-01-01T09:00:00,2024-01-01T09:30:00,bob\n"
    "c10002,Register,2024-01-02T08:00:00,2024-01-02T08:05:00,ann\n"
    "c10002,Approve,2024-01-03T08:00:00,2024-01-03T08:20:00,bob\n"
)
XES = """<?xml version="1.0" encoding="UTF-8"?>
<log xes.version="1.0" xmlns="http://www.xes-standard.org/">
 <trace><string key="concept:name" value="c10001"/>
  <event><string key="concept:name" value="Register"/><string key="lifecycle:transition" value="start"/>
   <date key="time:timestamp" value="2024-01-01T08:00:00+01:00"/><string key="org:resource" value="ann"/></event>
  <event><string key="concept:name" value="Register"/><string key="lifecycle:transition" value="complete"/>
   <date key="time:timestamp" value="2024-01-01T08:10:00+01:00"/><string key="org:resource" value="ann"/></event>
  <event><string key="concept:name" value="Check"/><string key="lifecycle:transition" value="complete"/>
   <date key="time:timestamp" value="2024-01-01T09:30:00+01:00"/><string key="org:resource" value="bob"/></event>
 </trace>
 <trace><string key="concept:name" value="c10002"/>
  <event><string key="concept:name" value="Approve"/><string key="lifecycle:transition" value="complete"/>
   <date key="time:timestamp" value="2024-01-03T08:20:00+01:00"/><string key="org:resource" value="bob"/></event>
 </trace>
</log>
"""


def _source(path: Path, dataset: str = "prova") -> inv.Source:
    return inv.Source(dataset, path.name, path.stat().st_size, lambda: path.open("rb"), path)


def _empty_development() -> inv.DevelopmentReference:
    return inv.DevelopmentReference({}, [])


def test_csv_log_counts_cases_events_activities_period_resources(tmp_path: Path):
    path = tmp_path / "log.csv.gz"
    path.write_bytes(gzip.compress(CSV.encode()))
    acc = inv.read_log(_source(path))
    stats = inv.stats(acc, _source(path), ORIGIN)
    assert (stats.cases, stats.events, stats.activities, stats.resources) == (2, 4, 3, 2)
    assert (stats.first, stats.last) == ("2024-01-01", "2024-01-03")
    assert (stats.start_share, stats.end_share, stats.observability) == (1.0, 1.0, "completa")


def test_xes_log_is_read_in_streaming_with_lifecycle(tmp_path: Path):
    path = tmp_path / "log.xes"
    path.write_text(XES)
    acc = inv.read_log(_source(path))
    stats = inv.stats(acc, _source(path), ORIGIN)
    assert (stats.cases, stats.events, stats.activities, stats.resources) == (2, 4, 3, 2)
    assert stats.start_share == pytest.approx(1 / 3, abs=1e-3)  # un inizio su tre attivita' completate
    assert stats.observability == "parziale"
    assert stats.first == "2024-01-01"  # 08:00+01:00 e' 07:00 UTC dello stesso giorno


def test_a_table_without_case_and_activity_is_not_a_log(tmp_path: Path):
    path = tmp_path / "measures.csv"
    path.write_text("log,metric,value\nA,W1,3.2\n")
    assert inv.read_log(_source(path)) is None


def test_simulated_logs_are_synthetic_even_with_full_observability(tmp_path: Path):
    folder = tmp_path / "simulated"
    folder.mkdir()
    path = folder / "run_0.csv"
    path.write_text(CSV)
    source = inv.Source("prova", "simulated/run_0.csv", path.stat().st_size, lambda: path.open("rb"))
    origin = inv.Origin("misto", "prova", "prova", ("simulated",))
    assert inv.stats(inv.read_log(source), source, origin).observability == "sintetico"


def _signature(text: str, label: str) -> inv.Signature:
    source = inv.Source("x", f"{label}.csv", len(text), lambda: io.BytesIO(text.encode()))
    return inv.signature(inv.read_csv(source), label, "x")


def test_same_content_in_another_form_is_recognized():
    reordered = CSV.splitlines()[0] + "\n" + "\n".join(reversed(CSV.splitlines()[1:])) + "\n"
    assert inv.compare(_signature(CSV, "a"), _signature(reordered, "b")) == "stesso contenuto di b"


def test_a_partition_is_contained_and_the_whole_contains_it():
    part = "\n".join(CSV.splitlines()[:3]) + "\n"  # solo il caso c10001
    whole, piece = _signature(CSV, "intero"), _signature(part, "parte")
    assert inv.compare(piece, whole).startswith("casi contenuti in intero")
    assert inv.compare(whole, piece).startswith("contiene i casi di parte")


def test_recoded_activities_still_match_on_distinctive_case_ids():
    recoded = CSV.replace("Register", "1").replace("Check", "2").replace("Approve", "3")
    assert inv.compare(_signature(recoded, "codificato"), _signature(CSV, "originale")).startswith("stessi casi di originale")


def test_same_process_with_other_cases_is_declared():
    other = CSV.replace("c1000", "s9")  # stesso processo, casi simulati con altri id
    assert inv.compare(_signature(other, "simulato"), _signature(CSV, "reale")).startswith("stesso processo di reale")


def test_short_case_ids_alone_do_not_make_two_logs_the_same():
    a = "case_id,activity,end_time\n1,x,2024-01-01T00:00:00\n2,y,2024-01-01T00:00:00\n"
    b = "case_id,activity,end_time\n1,p,2024-01-01T00:00:00\n2,q,2024-01-01T00:00:00\n"
    assert inv.compare(_signature(a, "a"), _signature(b, "b")) is None


def _holdout_reference() -> tuple[inv.HoldoutReference, bytes]:
    payload = b"contenuto congelato di un holdout di prova\n"
    reference = inv.holdout_reference()
    reference.by_hash[hashlib.sha256(payload).hexdigest()] = "prova_holdout"
    return reference, payload


def test_a_file_named_like_a_holdout_is_marked_and_never_parsed(tmp_path: Path, monkeypatch):
    ident = protocol.load_lock()["holdouts"][0]
    name = Path(ident["files"][0]["path"]).name
    payload = b"case_id,activity,end_time\n"
    path = tmp_path / name
    path.write_bytes(payload)
    monkeypatch.setattr(inv, "read_log", lambda source: pytest.fail("un holdout non si legge"))
    inventory = inv.Inventory()
    with protocol.selection_phase():
        inv.inspect(_source(path), inventory, inv.holdout_reference(), _empty_development(), ORIGIN, skip_archive=False)
    [record] = inventory.records
    assert record.holdout.startswith(f"holdout:{ident['id']}")
    assert name not in record.path and "[nome di un holdout" in record.path
    assert record.sha256 == hashlib.sha256(payload).hexdigest()  # l'impronta si', il contenuto no


def test_a_copy_of_a_frozen_holdout_with_an_innocent_name_is_marked(tmp_path: Path, monkeypatch):
    reference, payload = _holdout_reference()
    path = tmp_path / "copia_innocente.csv"
    path.write_bytes(payload)
    monkeypatch.setattr(inv, "read_log", lambda source: pytest.fail("un holdout non si legge"))
    inventory = inv.Inventory()
    inv.inspect(_source(path), inventory, reference, _empty_development(), ORIGIN, skip_archive=False)
    [record] = inventory.records
    assert record.holdout == "holdout:prova_holdout (impronta)"


def test_holdout_named_member_inside_an_archive_is_not_parsed(tmp_path: Path, monkeypatch):
    ident = protocol.load_lock()["holdouts"][-1]
    name = Path(ident["files"][0]["path"]).name
    archive = tmp_path / "pacchetto.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(f"logs/{name}", b"<log/>")
        bundle.writestr("logs/ordinario.csv", CSV)
    parsed: list[str] = []
    original = inv.read_log
    monkeypatch.setattr(inv, "read_log", lambda source: parsed.append(source.path) or original(source))
    inventory = inv.Inventory()
    with protocol.selection_phase():
        inv.inspect(_source(archive), inventory, inv.holdout_reference(), _empty_development(), ORIGIN, skip_archive=False)
    assert parsed == ["pacchetto.zip!logs/ordinario.csv"]
    held = [r for r in inventory.records if r.holdout]
    assert len(held) == 1 and name not in held[0].path


def test_development_copy_is_found_by_hash_and_name(tmp_path: Path):
    path = tmp_path / "BPIC_2012_copy.csv"
    path.write_text(CSV)
    digest = hashlib.sha256(CSV.encode()).hexdigest()
    development = inv.DevelopmentReference({digest: "datasets/x.csv"}, [])
    inventory = inv.Inventory()
    inv.inspect(_source(path), inventory, inv.holdout_reference(), development, ORIGIN, skip_archive=False)
    [record] = inventory.records
    assert "stessa impronta di datasets/x.csv" in record.development
    assert "nome simile a BPIC 2012" in record.development


def test_the_committed_report_does_not_name_a_holdout():
    """Il report sta in tests/simulation: il test dei nomi di PROTO-01 lo controlla gia'; qui il redatto."""
    assert inv.redacted("a/b!c/x.csv", "id") == "a/b!c/[nome di un holdout: id]"


def test_long_numeric_ids_of_another_process_are_not_the_same_cases():
    """Gli oggetti di un OCEL con id numerici lunghi non 'contengono' i casi di un log di un altro processo."""
    other = CSV.replace("Register", "Create PO").replace("Check", "Receive goods").replace("Approve", "Pay invoice")
    assert inv.compare(_signature(other, "acquisti"), _signature(CSV, "prestiti")) is None


def test_json_keeps_the_strongest_relations_first():
    record = {"development": ["nome simile a X", "stesso processo di A", "stessa impronta di B"], "radar": []}
    assert inv._compact(record)["development"][0] == "stessa impronta di B"


def test_compact_and_epoch_instants():
    assert inv.parse_instant("20120315093000").year == 2012
    assert inv.parse_instant("1325376000").year == 2012  # secondi
    assert inv.parse_instant("1325376000000").year == 2012  # millisecondi
    assert inv.parse_instant("1325376000000000000").year == 2012  # nanosecondi
    assert inv.parse_instant("9" * 30) is None


def test_a_decompressed_copy_of_a_frozen_holdout_is_marked(tmp_path: Path, monkeypatch):
    payload = CSV.encode()
    reference = inv.holdout_reference()
    reference.by_hash[hashlib.sha256(payload).hexdigest()] = "prova_holdout"  # come _unpacked_fingerprints
    path = tmp_path / "copia.csv.gz"
    path.write_bytes(gzip.compress(payload))  # ricompresso: impronta del file diversa, contenuto uguale
    monkeypatch.setattr(inv, "read_log", lambda source: pytest.fail("un holdout non si legge"))
    inventory = inv.Inventory()
    inv.inspect(_source(path), inventory, reference, _empty_development(), ORIGIN, skip_archive=False)
    assert inventory.records[0].holdout == "holdout:prova_holdout (impronta)"


def test_holdout_fingerprints_include_the_unpacked_content(tmp_path: Path):
    gz = tmp_path / "x.csv.gz"
    gz.write_bytes(gzip.compress(b"abc"))
    archive = tmp_path / "x.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("inner.csv", b"abc")
    expected = hashlib.sha256(b"abc").hexdigest()
    assert inv._unpacked_fingerprints(gz) == [expected]
    assert inv._unpacked_fingerprints(archive) == [expected]


def test_a_large_ocel_without_ijson_is_reported_not_lost(tmp_path: Path, monkeypatch):
    path = tmp_path / "big.json"
    path.write_text('{"objectTypes": [], "eventTypes": [], "events": [], "objects": []}')
    monkeypatch.setattr(inv, "MAX_OCEL_JSON", 1)
    monkeypatch.setattr(inv, "_ocel_stream", lambda source, acc: False)
    inventory = inv.Inventory()
    inv.inspect(_source(path), inventory, inv.holdout_reference(), _empty_development(), ORIGIN, skip_archive=False)
    assert "ijson" in inventory.records[0].note


def test_code_with_a_name_like_a_holdout_is_not_a_holdout():
    reference = inv.holdout_reference()
    ident = protocol.load_lock()["holdouts"][0]["names"][0]
    code = inv.Source("prova", f"examples/{ident}Queue.py", 1, lambda: io.BytesIO(b""))
    log = inv.Source("prova", f"examples/{ident}Queue.csv", 1, lambda: io.BytesIO(b""))
    assert inv.holdout_by_name(code, reference) is None
    assert inv.holdout_by_name(log, reference) is not None


def test_an_archive_closed_by_a_lock_is_named_after_its_holdout():
    reference = inv.holdout_reference()
    container, owner = next(iter(reference.containers.items()))
    source = inv.Source("prova", container, 1, lambda: io.BytesIO(b""))
    assert inv.holdout_by_name(source, reference) == owner
