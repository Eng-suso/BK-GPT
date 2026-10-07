"""Dove stanno i file originali delle fonti: un'interfaccia, un'implementazione locale.

Prima l'upload scriveva in `Path("data") / storage_key` e worker, download e
cancellazione rileggevano lo stesso percorso. Due difetti:

- `Path("data")` e' relativo alla cartella da cui parte il processo: un worker
  avviato altrove non trova i file che l'API ha scritto;
- il dominio sapeva che i file stanno su un disco. Con piu' macchine, o con un
  object storage, ogni chiamante andava riscritto.

Qui il dominio parla con `SourceBlobStore` (put, get, delete) per chiave. Le
chiavi restano quelle gia' salvate nel database (`source_uploads/<tenant>/
<hash><ext>`), quindi nessuna migrazione. Oggi l'implementazione e'
`LocalBlobStore`, con radice assoluta (`SOURCE_STORAGE_ROOT`, o `data/` nella
radice del progetto); un archivio remoto implementera' lo stesso protocollo.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from backend.settings import settings

# La radice del progetto: `backend/workspace_services/blob_store.py` -> repo.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
# Tutte le chiavi delle fonti vivono qui sotto: e' il confine dei percorsi.
_SOURCES_PREFIX = "source_uploads"
# Il download legge e manda a pezzi: piu' download insieme non tengono in
# memoria un file intero ciascuno.
STREAM_CHUNK_BYTES = 1024 * 1024


class BlobKeyError(ValueError):
    """La chiave non indica un file delle fonti (vuota, o fuori dal confine)."""


class BlobNotFound(LookupError):
    """Nessun file per questa chiave."""


class SourceBlobStore(Protocol):
    def put(self, key: str, payload: bytes, *, content_hash: str) -> None:
        """Scrive il file. Idempotente per `content_hash`."""
        ...

    def get(self, key: str) -> bytes:
        """I byte del file; `BlobNotFound` se non c'e'."""
        ...

    def stream(self, key: str) -> Iterator[bytes]:
        """Il file a pezzi. `BlobNotFound` subito, prima del primo pezzo."""
        ...

    def delete(self, key: str) -> None:
        """Rimuove il file; un file gia' assente non e' un errore."""
        ...


class LocalBlobStore:
    """File su disco sotto una radice assoluta, scritti in modo atomico."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    @property
    def root(self) -> Path:
        return self._root

    def _path(self, key: str) -> Path:
        if not key:
            raise BlobKeyError("Chiave del file vuota.")
        boundary = (self._root / _SOURCES_PREFIX).resolve()
        candidate = (self._root / key).resolve()
        if boundary not in candidate.parents:
            raise BlobKeyError("Percorso della fonte non valido.")
        return candidate

    def put(self, key: str, payload: bytes, *, content_hash: str) -> None:
        destination = self._path(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Il nome e' l'hash del contenuto: un file gia' presente e integro non
        # si riscrive. Uno troncato da un crash o da un disco pieno si',
        # altrimenti ogni caricamento dello stesso file servirebbe i byte rotti.
        if destination.exists() and hashlib.sha256(destination.read_bytes()).hexdigest() == content_hash:
            return
        # Scrittura atomica: chi legge vede il file vecchio o quello completo,
        # mai uno a meta', anche con due caricamenti dello stesso file insieme.
        temporary = destination.with_name(f"{destination.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_bytes(payload)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)

    def get(self, key: str) -> bytes:
        path = self._path(key)
        try:
            return path.read_bytes()
        except FileNotFoundError as exc:
            raise BlobNotFound(key) from exc

    def stream(self, key: str) -> Iterator[bytes]:
        path = self._path(key)
        try:
            handle = path.open("rb")
        except FileNotFoundError as exc:
            raise BlobNotFound(key) from exc

        def chunks() -> Iterator[bytes]:
            with handle:
                while chunk := handle.read(STREAM_CHUNK_BYTES):
                    yield chunk

        return chunks()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


def storage_root() -> Path:
    """La radice dei file: configurata, o `data/` nella radice del progetto.

    Un valore relativo si legge dalla radice del progetto, mai dalla cartella
    di lavoro: API e worker partiti da cartelle diverse devono vedere lo stesso
    archivio. Chi prima avviava l'app da un'altra cartella aveva i file in
    `<quella cartella>/data`: per ritrovarli basta indicarla qui, assoluta.
    """
    configured = settings.source_storage_root
    if not configured:
        return _PROJECT_ROOT / "data"
    root = Path(configured)
    return root if root.is_absolute() else _PROJECT_ROOT / root


@lru_cache(maxsize=1)
def source_blob_store() -> SourceBlobStore:
    return LocalBlobStore(storage_root())


def source_key(tenant_id: str, content_hash: str, extension: str) -> str:
    """La chiave di un file: per tenant (con hash, non in chiaro) e per contenuto."""
    tenant_key = hashlib.sha256(tenant_id.encode()).hexdigest()[:20]
    return f"{_SOURCES_PREFIX}/{tenant_key}/{content_hash}{extension}"
