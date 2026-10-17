"""SIM-36: i log pubblici del benchmark, scaricati e verificati.

Due log BPIC sotto i 4TU General Terms of Use. Il BPIC 2020 e' CC BY-NC: escluso.
Il file si scarica una volta in una cache locale e si accetta solo se il suo MD5
coincide con quello che 4TU dichiara nei metadati del file: nessun MD5 scritto a
mano qui, nessun mirror non verificato. Con 4TU in manutenzione (503
``StorageMaintenance``) il download fallisce e il benchmark si riprova dopo.

Da verificare al primo accesso alla rete: l'API dei file di 4TU (Djehuty,
``/v2/articles/<uuid>/files``) restituisce per ogni file ``name``,
``download_url`` e l'MD5 in ``computed_md5`` o ``supplied_md5``. Se la forma
cambia, ``_file_entry`` lo dice invece di scaricare alla cieca.
"""

from __future__ import annotations

import gzip
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from backend.eventlog.mapping import ColumnMapping, apply_mapping
from backend.eventlog.model import EventLog
from backend.eventlog.readers import read_xes

API = "https://data.4tu.nl/v2/articles"

# I log BPIC sono XES con una riga per transizione (start/complete).
XES_MAPPING = ColumnMapping(
    case_id=("case:concept:name",),
    activity=("concept:name",),
    timestamp="time:timestamp",
    lifecycle="lifecycle:transition",
    resource="org:resource",
)


@dataclass(frozen=True, slots=True)
class Dataset:
    key: str
    title: str
    doi: str
    # L'uuid dell'articolo su 4TU, lo stesso del DOI storico.
    article_uuid: str
    file_name: str
    license: str


DATASETS: dict[str, Dataset] = {
    "bpic2012": Dataset(
        key="bpic2012",
        title="BPI Challenge 2012 (richieste di prestito)",
        doi="10.4121/uuid:3926db30-f712-4394-aebc-75976070e91f",
        article_uuid="3926db30-f712-4394-aebc-75976070e91f",
        file_name="BPI_Challenge_2012.xes.gz",
        license="4TU General Terms of Use",
    ),
    "bpic2013_incidents": Dataset(
        key="bpic2013_incidents",
        title="BPI Challenge 2013, incidenti (Volvo IT)",
        doi="10.4121/uuid:500573e6-accc-4b0c-9576-aa5468b10cee",
        article_uuid="500573e6-accc-4b0c-9576-aa5468b10cee",
        file_name="BPI_Challenge_2013_incidents.xes.gz",
        license="4TU General Terms of Use",
    ),
}


class DatasetUnavailable(RuntimeError):
    """4TU non risponde, o il file non e' quello dichiarato."""


def cache_dir() -> Path:
    return Path(os.environ.get("DELIR_BENCHMARK_CACHE", Path.home() / ".cache" / "delir-benchmark"))


def md5_of(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_entry(files: Any, dataset: Dataset) -> tuple[str, str]:
    """(URL di download, MD5 dichiarato) del file del dataset nei metadati di 4TU."""
    if not isinstance(files, list):
        raise DatasetUnavailable(f"4TU ha risposto con metadati inattesi per {dataset.key}.")
    for entry in files:
        if isinstance(entry, dict) and entry.get("name") == dataset.file_name:
            url = entry.get("download_url")
            md5 = entry.get("computed_md5") or entry.get("supplied_md5")
            if not url or not md5:
                raise DatasetUnavailable(f"4TU non dichiara URL e MD5 di {dataset.file_name}: niente download non verificato.")
            return str(url), str(md5).lower()
    raise DatasetUnavailable(f"{dataset.file_name} non e' fra i file dell'articolo {dataset.doi}.")


def fetch(dataset: Dataset, *, client: httpx.Client | None = None) -> Path:
    """Il file del dataset nella cache, scaricato e verificato se manca."""
    target = cache_dir() / dataset.file_name
    owned = client is None
    http = client or httpx.Client(timeout=120, follow_redirects=True)
    try:
        response = http.get(f"{API}/{dataset.article_uuid}/files")
        if response.status_code != 200:
            raise DatasetUnavailable(f"4TU risponde {response.status_code} per {dataset.key}: riprova piu' tardi.")
        url, expected = _file_entry(response.json(), dataset)
        if target.exists() and md5_of(target) == expected:
            return target
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(target.suffix + ".part")
        with http.stream("GET", url) as stream:
            if stream.status_code != 200:
                raise DatasetUnavailable(f"Download di {dataset.file_name}: risposta {stream.status_code}.")
            with partial.open("wb") as handle:
                for chunk in stream.iter_bytes():
                    handle.write(chunk)
        actual = md5_of(partial)
        if actual != expected:
            partial.unlink(missing_ok=True)
            raise DatasetUnavailable(f"MD5 di {dataset.file_name} diverso da quello di 4TU ({actual} invece di {expected}): file scartato.")
        partial.replace(target)
        return target
    except httpx.HTTPError as exc:
        raise DatasetUnavailable(f"4TU non raggiungibile per {dataset.key}: {exc}.") from exc
    finally:
        if owned:
            http.close()


def load(path: Path) -> EventLog:
    """Il log XES (anche ``.xes.gz``) come event log canonico."""
    payload = path.read_bytes()
    if path.suffix == ".gz":
        payload = gzip.decompress(payload)
    log, _ = apply_mapping(read_xes(payload), XES_MAPPING, source_name=path.name)
    return log
