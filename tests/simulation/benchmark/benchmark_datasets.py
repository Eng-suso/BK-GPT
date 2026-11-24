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

from backend.eventlog.mapping import ColumnMapping, apply_mapping
from backend.eventlog.model import EventLog
from backend.eventlog.readers import read_xes
from scripts import fetch_datasets

# BPIC 2012: una riga per transizione (start/complete).
_TRANSITIONS = ColumnMapping(
    case_id=("case:concept:name",),
    activity=("concept:name",),
    timestamp="time:timestamp",
    lifecycle="lifecycle:transition",
    resource="org:resource",
)
# BPIC 2013: ogni riga e' un cambio di stato istantaneo. Il ciclo di vita non e'
# start/complete ma il sottostato ("Accepted" + "In Progress"): fa parte
# dell'attivita', come nella letteratura sul log.
_STATUS_CHANGES = ColumnMapping(
    case_id=("case:concept:name",),
    activity=("concept:name", "lifecycle:transition"),
    end="time:timestamp",
    resource="org:resource",
)


@dataclass(frozen=True, slots=True)
class Dataset:
    key: str
    manifest_id: str
    title: str
    doi: str
    file_name: str
    license: str
    mapping: ColumnMapping


DATASETS: dict[str, Dataset] = {
    "bpic2012": Dataset(
        key="bpic2012",
        manifest_id="bpic2012",
        title="BPI Challenge 2012 (richieste di prestito)",
        doi="10.4121/uuid:3926db30-f712-4394-aebc-75976070e91f",
        file_name="BPI_Challenge_2012.xes.gz",
        license="4TU General Terms of Use",
        mapping=_TRANSITIONS,
    ),
    "bpic2013_incidents": Dataset(
        key="bpic2013_incidents",
        manifest_id="bpic2013-incidents",
        title="BPI Challenge 2013, incidenti (Volvo IT)",
        doi="10.4121/uuid:500573e6-accc-4b0c-9576-aa5468b10cee",
        file_name="BPI_Challenge_2013_incidents.xes.gz",
        license="4TU General Terms of Use",
        mapping=_STATUS_CHANGES,
    ),
}


class DatasetUnavailable(RuntimeError):
    """4TU non risponde, o il file non e' quello dichiarato nel manifest."""


def fetch(dataset: Dataset) -> Path:
    """Il file del dataset nella cache di ``fetch_datasets``, scaricato e verificato se manca."""
    try:
        entry = fetch_datasets.load_manifest()[dataset.manifest_id]
        folder = fetch_datasets.fetch(entry)
    except (fetch_datasets.DatasetError, OSError) as exc:
        raise DatasetUnavailable(f"{dataset.key}: {exc}") from exc
    return folder / dataset.file_name


def load(path: Path, mapping: ColumnMapping) -> EventLog:
    """Il log XES (anche ``.xes.gz``) come event log canonico, letto con la mappatura del dataset."""
    payload = path.read_bytes()
    if path.suffix == ".gz":
        payload = gzip.decompress(payload)
    log, _ = apply_mapping(read_xes(payload), mapping, source_name=path.name)
    return log
