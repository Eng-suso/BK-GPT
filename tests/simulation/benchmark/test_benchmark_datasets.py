"""SIM-36: download verificato dei log pubblici, senza rete (transport finto)."""

import gzip
import hashlib

import httpx
import pytest

from tests.simulation.benchmark.benchmark_datasets import DATASETS, DatasetUnavailable, fetch, load

DATASET = DATASETS["bpic2012"]
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
PAYLOAD = gzip.compress(XES)


def _client(*, md5: str | None = None, status: int = 200, body: bytes = PAYLOAD) -> tuple[httpx.Client, list[str]]:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/files"):
            if status != 200:
                return httpx.Response(status, json={"error": "StorageMaintenance"})
            return httpx.Response(200, json=[
                {"name": "readme.txt", "download_url": "https://data.4tu.nl/file/readme", "computed_md5": "x"},
                {"name": DATASET.file_name, "download_url": "https://data.4tu.nl/file/log", "computed_md5": md5 or hashlib.md5(body).hexdigest()},
            ])
        return httpx.Response(200, content=body)

    return httpx.Client(transport=httpx.MockTransport(handler)), calls


@pytest.fixture(autouse=True)
def _cache(tmp_path, monkeypatch):
    monkeypatch.setenv("DELIR_BENCHMARK_CACHE", str(tmp_path))


def test_the_file_is_kept_only_with_the_md5_of_4tu(tmp_path):
    client, calls = _client()

    path = fetch(DATASET, client=client)

    assert path == tmp_path / DATASET.file_name
    assert path.read_bytes() == PAYLOAD
    assert calls == [f"/v2/articles/{DATASET.article_uuid}/files", "/file/log"]


def test_a_cached_file_with_the_right_md5_is_not_downloaded_again():
    fetch(DATASET, client=_client()[0])
    client, calls = _client()

    fetch(DATASET, client=client)

    assert calls == [f"/v2/articles/{DATASET.article_uuid}/files"]


def test_a_different_md5_discards_the_file(tmp_path):
    with pytest.raises(DatasetUnavailable, match="MD5"):
        fetch(DATASET, client=_client(md5="0" * 32)[0])

    assert not any(tmp_path.iterdir())


def test_maintenance_says_to_retry_later():
    with pytest.raises(DatasetUnavailable, match="503"):
        fetch(DATASET, client=_client(status=503)[0])


def test_a_downloaded_log_becomes_a_canonical_event_log():
    log = load(fetch(DATASET, client=_client()[0]))

    assert [e.activity for e in log.events] == ["A_SUBMITTED", "W_Afhandelen leads"]
    handled = log.events[1]
    assert handled.start is not None and (handled.end - handled.start).total_seconds() == pytest.approx(507.48)
    assert handled.resource == "10862"


def _two_cases_xes() -> bytes:
    trace = """  <trace><string key="concept:name" value="{case}"/>
    <event><string key="concept:name" value="Ricevi"/><string key="lifecycle:transition" value="START"/><string key="org:resource" value="anna"/><date key="time:timestamp" value="2011-10-0{day}T09:00:00+02:00"/></event>
    <event><string key="concept:name" value="Ricevi"/><string key="lifecycle:transition" value="COMPLETE"/><string key="org:resource" value="anna"/><date key="time:timestamp" value="2011-10-0{day}T09:{minutes}:00+02:00"/></event>
  </trace>"""
    body = "\n".join(trace.format(case=i, day=i + 1, minutes=10 * (i + 1)) for i in range(4))
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<log xmlns="http://www.xes-standard.org/">\n{body}\n</log>'.encode()


def test_the_baseline_is_measured_or_says_why_not(tmp_path):
    import json

    from tests.simulation.benchmark.run_baseline import run

    out = tmp_path / "baseline.json"
    client, _ = _client(body=gzip.compress(_two_cases_xes()))

    assert run(["bpic2012"], out, client=client) == 0
    result = json.loads(out.read_text())["results"][0]
    assert result["status"] == "measured"
    assert result["cases"] == {"A": 2, "B": 2}
    assert result["efficiency"]["human_configuration_minutes"] is None
    # A: casi da 10 e 20 minuti, B: da 30 e 40. Lo scarto medio e' 20 minuti su 35.
    assert result["metrics"]["cycle_time_distribution"] == pytest.approx(20 / 35, rel=1e-3)

    assert run(["bpic2012"], out, client=_client(status=503)[0]) == 1
    assert json.loads(out.read_text())["results"][0]["status"] == "unavailable"
