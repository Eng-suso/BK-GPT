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
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from backend.settings import settings

# La radice del progetto: `backend/workspace_services/blob_store.py` -> repo.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
# Tutte le chiavi delle fonti vivono qui sotto: e' il confine dei percorsi.
_SOURCES_PREFIX = "source_uploads"


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

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


def storage_root() -> Path:
    """La radice dei file: configurata, o `data/` nella radice del progetto."""
    configured = settings.source_storage_root
    return Path(configured) if configured else _PROJECT_ROOT / "data"


@lru_cache(maxsize=1)
def source_blob_store() -> SourceBlobStore:
    return LocalBlobStore(storage_root())


def source_key(tenant_id: str, content_hash: str, extension: str) -> str:
    """La chiave di un file: per tenant (con hash, non in chiaro) e per contenuto."""
    tenant_key = hashlib.sha256(tenant_id.encode()).hexdigest()[:20]
    return f"{_SOURCES_PREFIX}/{tenant_key}/{content_hash}{extension}"
