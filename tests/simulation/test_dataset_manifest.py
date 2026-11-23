"""Il catalogo dei dataset e' coerente con cio' che c'e' nel repo.

Nessun accesso alla rete: controlla solo il manifest e i file vendored.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "fetch_datasets", ROOT / "scripts" / "fetch_datasets.py"
)
assert SPEC and SPEC.loader
fetch_datasets = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fetch_datasets)

MANIFEST = fetch_datasets.load_manifest()
MD5 = re.compile(r"^[0-9a-f]{32}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
REDISTRIBUTABLE = {"CC-BY-4.0", "Apache-2.0"}


def test_duplicate_ids_are_rejected(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        '{"datasets": [{"id": "a", "mode": "fetch"}, {"id": "a", "mode": "fetch"}]}',
        encoding="utf-8",
    )
    with pytest.raises(fetch_datasets.DatasetError):
        fetch_datasets.load_manifest(manifest)


def test_modes_licences_and_sources_are_declared() -> None:
    assert MANIFEST, "manifest vuoto"
    for entry in MANIFEST.values():
        assert entry["mode"] in {"vendored", "fetch", "academic"}, entry["id"]
        assert entry["license"], entry["id"]
        assert entry["source"].startswith("https://"), entry["id"]


@pytest.mark.parametrize(
    "entry",
    [e for e in MANIFEST.values() if e["mode"] == "vendored"],
    ids=lambda e: e["id"],
)
def test_vendored_datasets_are_present_and_redistributable(entry: dict) -> None:
    path = ROOT / entry["path"]
    assert path.is_dir() and any(path.iterdir()), f"{path} mancante"
    assert entry["license"] in REDISTRIBUTABLE, (
        f"{entry['id']}: {entry['license']} non si ripubblica in un repo pubblico"
    )
    attribution = path / "ATTRIBUTION.md"
    if not attribution.exists():
        attribution = path.parent / "ATTRIBUTION.md"
    assert attribution.exists(), f"{entry['id']}: manca ATTRIBUTION.md"


@pytest.mark.parametrize(
    "entry",
    [e for e in MANIFEST.values() if e["mode"] != "vendored"],
    ids=lambda e: e["id"],
)
def test_downloadable_datasets_are_pinned(entry: dict) -> None:
    if "git" in entry:
        assert COMMIT.match(entry["git_commit"]), entry["id"]
        return
    for item in entry.get("files") or [entry]:
        assert item["url"].startswith("https://"), entry["id"]
        assert MD5.match(item["md5"]), entry["id"]
        assert item["bytes"] > 0, entry["id"]


def test_noncommercial_data_needs_explicit_opt_in() -> None:
    academic = [e for e in MANIFEST.values() if "NC" in e["license"]]
    assert academic, "il caso non commerciale non e' coperto"
    for entry in academic:
        assert entry["mode"] == "academic", entry["id"]
        with pytest.raises(fetch_datasets.DatasetError):
            fetch_datasets.fetch(entry)


def test_extraneous_delays_inputs_have_the_expected_processes() -> None:
    synthetic = ROOT / "datasets/extraneous-delays/inputs/synthetic"
    for process in (
        "Insurance_Claims",
        "Loan_Application",
        "Pharmacy",
        "Procure_to_Pay",
    ):
        for variant in ("", "_1_timer", "_3_timers", "_5_timers"):
            for ext in (".bpmn", ".json", ".csv.gz"):
                assert (synthetic / f"{process}{variant}{ext}").exists(), (
                    f"{process}{variant}{ext}"
                )
