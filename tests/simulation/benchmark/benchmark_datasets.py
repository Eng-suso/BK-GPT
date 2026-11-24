"""SIM-36: i log pubblici del benchmark, scaricati e verificati.

Due log BPIC sotto i 4TU General Terms of Use. Il BPIC 2020 e' CC BY-NC: escluso.
Il download e' quello di ``scripts/fetch_datasets.py``: URL e MD5 vengono da
``datasets/manifest.json`` e un file si accetta solo se l'MD5 coincide. I log
non entrano nel repo (la licenza 4TU non ne permette la ripubblicazione): stanno
nella cache di ``fetch_datasets`` (``DELIR_DATASETS_CACHE``). Con 4TU in
manutenzione o la rete chiusa il download fallisce e il motivo arriva al
chiamante come ``DatasetUnavailable``.
"""

from __future__ import annotations

import gzip
from dataclasses import dataclass
from pathlib import Path

from backend.eventlog.mapping import ColumnMapping, QualityReport, TimestampFormat, apply_mapping
from backend.eventlog.model import EventLog
from backend.eventlog.readers import read_xes
from scripts import fetch_datasets

# Entrambi i log sono in ora dell'Europa centrale (+01/+02): i timestamp XES hanno
# il fuso, e il gemello ingenuo sposta il calendario in questa zona.
_CET = TimestampFormat(timezone="Europe/Amsterdam")
# BPIC 2012: una riga per transizione (start/complete).
_TRANSITIONS = ColumnMapping(
    case_id=("case:concept:name",),
    activity=("concept:name",),
    timestamp="time:timestamp",
    lifecycle="lifecycle:transition",
    resource="org:resource",
    timestamps=_CET,
)
# BPIC 2013: ogni riga e' un cambio di stato istantaneo. Il ciclo di vita non e'
# start/complete ma il sottostato ("Accepted" + "In Progress"): fa parte
# dell'attivita', come nella letteratura sul log.
_STATUS_CHANGES = ColumnMapping(
    case_id=("case:concept:name",),
    activity=("concept:name", "lifecycle:transition"),
    end="time:timestamp",
    resource="org:resource",
    timestamps=_CET,
)


@dataclass(frozen=True, slots=True)
class Dataset:
    """Un log del benchmark: titolo, fonte, licenza, URL e MD5 stanno nel manifest."""

    key: str
    manifest_id: str
    mapping: ColumnMapping
    # Perche' il log non serve a giudicare una previsione A -> B; None se serve.
    unsuitable_for_a_to_b: str | None = None


DATASETS: dict[str, Dataset] = {
    d.key: d
    for d in (
        Dataset("bpic2012", "bpic2012", _TRANSITIONS),
        Dataset(
            "bpic2013_incidents",
            "bpic2013-incidents",
            _STATUS_CHANGES,
            unsuitable_for_a_to_b=(
                "foto degli incidenti aperti a maggio 2012, non un flusso: con ogni taglio il 100% dei casi "
                "di B e' troncato dalla fine del log (decisione di Sohayb, 2026-11-24)"
            ),
        ),
    )
}


class DatasetUnavailable(RuntimeError):
    """4TU non risponde, o il file non e' quello dichiarato nel manifest."""


def manifest_entry(manifest_id: str) -> dict:
    return fetch_datasets.load_manifest()[manifest_id]


def fetch(dataset: Dataset) -> Path:
    """Il file del dataset nella cache di ``fetch_datasets``, scaricato e verificato se manca."""
    try:
        entry = manifest_entry(dataset.manifest_id)
        return fetch_datasets.fetch(entry) / entry["file"]
    except (fetch_datasets.DatasetError, OSError) as exc:
        raise DatasetUnavailable(f"{dataset.key}: {exc}") from exc


def load(path: Path, mapping: ColumnMapping) -> tuple[EventLog, QualityReport]:
    """Il log XES (anche ``.xes.gz``) come event log canonico, con il report delle righe scartate.

    In BPIC 2012 le righe ``SCHEDULE`` non sono ne' inizio ne' fine: il report le
    conta come ``unknown_lifecycle`` e la baseline lo scrive.
    """
    payload = path.read_bytes()
    if path.suffix == ".gz":
        payload = gzip.decompress(payload)
    return apply_mapping(read_xes(payload), mapping, source_name=path.name)
