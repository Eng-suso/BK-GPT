"""SIM-36: download verificato dei log pubblici e lettura XES, senza rete.

Il manifest di prova punta a file locali (``file://``): ``fetch_datasets`` li
scarica con lo stesso codice che usa per 4TU, MD5 compreso.
"""

import gzip
import hashlib

import pytest

from scripts import fetch_datasets
from tests.simulation.benchmark.benchmark_datasets import DATASETS, DatasetUnavailable, fetch, load

BPIC2012 = DATASETS["bpic2012"]
BPIC2013 = DATASETS["bpic2013_incidents"]
XES = b"""<?xml version="1.0" encoding="UTF-8"?>
<log xmlns="http://www.xes-standard.org/">
  <trace><string key="concept:name" value="173688"/>
    <event><string key="concept:name" value="A_SUBMITTED"/><string key="lifecycle:transition" value="COMPLETE"/>
      <string key="org:resource" value="112"/><date key="time:timestamp" value="2011-10-01T00:38:44.546+02:00"/></event>
    <event><string key="concept:name" value="W_Afhandelen leads"/><string key="lifecycle:transition" value="START"/>
      <string key="org:resource" value="10862"/><date key="time:timestamp" value="2011-10-01T11:36:46.437+02:00"/></event>
    <event><string key="concept:name" value="W_Afhandelen leads"/><string key="lifecycle:transition" value="COMPLETE"/>
      <string key="org:resource" value="10862"/><date key="time:timestamp" value="2011-10-01T11:45:13.917+02:00"/></event>
  </trace>
</log>"""
STATUS_XES = b"""<?xml version="1.0" encoding="UTF-8"?>
<log xmlns="http://www.xes-standard.org/">
  <trace><string key="concept:name" value="1-364285768"/>
    <event><string key="concept:name" value="Accepted"/><string key="lifecycle:transition" value="In Progress"/>
      <string key="org:resource" value="Frederic"/><date key="time:timestamp" value="2010-03-31T16:59:42+02:00"/></event>
    <event><string key="concept:name" value="Completed"/><string key="lifecycle:transition" value="Closed"/>
      <string key="org:resource" value="Frederic"/><date key="time:timestamp" value="2010-04-01T10:00:00+02:00"/></event>
  </trace>
</log>"""


FILE = "log.xes.gz"


def serve(tmp_path, monkeypatch, dataset, body: bytes, *, md5: str | None = None) -> None:
    """Un manifest con il solo ``dataset``, servito da un file locale."""
    source = tmp_path / "source" / FILE
    source.parent.mkdir()
    source.write_bytes(body)
    entry = {
        "id": dataset.manifest_id, "mode": "fetch", "license": "4TU General Terms of Use",
        "url": source.as_uri(), "file": FILE, "md5": md5 or hashlib.md5(body).hexdigest(),
    }
    monkeypatch.setattr(fetch_datasets, "load_manifest", lambda: {dataset.manifest_id: entry})


@pytest.fixture(autouse=True)
def _cache(tmp_path, monkeypatch):
    monkeypatch.setenv("DELIR_DATASETS_CACHE", str(tmp_path / "cache"))


def test_the_benchmark_logs_are_in_the_manifest_with_their_licence():
    manifest = fetch_datasets.load_manifest()
    for dataset in DATASETS.values():
        entry = manifest[dataset.manifest_id]
        assert (entry["license"], entry["mode"]) == ("4TU General Terms of Use", "fetch")


def test_the_file_is_kept_only_with_the_md5_of_the_manifest(tmp_path, monkeypatch):
    serve(tmp_path, monkeypatch, BPIC2012, gzip.compress(XES))

    path = fetch(BPIC2012)

    assert path == tmp_path / "cache" / "bpic2012" / FILE
    assert gzip.decompress(path.read_bytes()) == XES


def test_a_different_md5_discards_the_file(tmp_path, monkeypatch):
    serve(tmp_path, monkeypatch, BPIC2012, gzip.compress(XES), md5="0" * 32)

    with pytest.raises(DatasetUnavailable, match="MD5"):
        fetch(BPIC2012)

    assert not any((tmp_path / "cache" / "bpic2012").iterdir())


def test_an_unreachable_source_says_why(tmp_path, monkeypatch):
    serve(tmp_path, monkeypatch, BPIC2012, gzip.compress(XES))
    (tmp_path / "source" / FILE).unlink()

    with pytest.raises(DatasetUnavailable, match="bpic2012"):
        fetch(BPIC2012)


def test_bpic2012_pairs_start_and_complete(tmp_path, monkeypatch):
    serve(tmp_path, monkeypatch, BPIC2012, gzip.compress(XES))

    log, quality = load(fetch(BPIC2012), BPIC2012.mapping)

    assert quality.rows_excluded == 0
    assert [e.activity for e in log.events] == ["A_SUBMITTED", "W_Afhandelen leads"]
    handled = log.events[1]
    assert handled.start is not None and (handled.end - handled.start).total_seconds() == pytest.approx(507.48)
    assert handled.resource == "10862"


def test_bpic2013_status_changes_are_instant_events(tmp_path, monkeypatch):
    # Il ciclo di vita di BPIC 2013 e' un sottostato, non start/complete: letto
    # come transizione, il log restava senza eventi.
    serve(tmp_path, monkeypatch, BPIC2013, gzip.compress(STATUS_XES))

    log, _ = load(fetch(BPIC2013), BPIC2013.mapping)

    assert [(e.activity, e.start) for e in log.events] == [("Accepted · In Progress", None), ("Completed · Closed", None)]
    assert {e.resource for e in log.events} == {"Frederic"}
