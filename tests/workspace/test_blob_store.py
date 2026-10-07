"""L'archivio dei file originali: stesse garanzie di prima, dietro un'interfaccia.

Senza database. Le garanzie che `store_original` aveva gia' (scrittura
atomica, file troncato riscritto, niente percorsi fuori dal confine) restano;
in piu' la radice non dipende dalla cartella da cui parte il processo.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from backend.workspace_services.blob_store import (
    BlobKeyError,
    BlobNotFound,
    LocalBlobStore,
    source_key,
    storage_root,
)

_PAYLOAD = b"Intervista al responsabile acquisti"
_HASH = hashlib.sha256(_PAYLOAD).hexdigest()


def _key() -> str:
    return source_key("tenant-a", _HASH, ".txt")


def test_a_stored_file_comes_back_byte_for_byte(tmp_path: Path):
    store = LocalBlobStore(tmp_path)

    store.put(_key(), _PAYLOAD, content_hash=_HASH)

    assert store.get(_key()) == _PAYLOAD


def test_a_truncated_file_is_rewritten_by_the_next_upload(tmp_path: Path):
    store = LocalBlobStore(tmp_path)
    store.put(_key(), _PAYLOAD, content_hash=_HASH)
    (tmp_path / _key()).write_bytes(_PAYLOAD[:5])

    store.put(_key(), _PAYLOAD, content_hash=_HASH)

    assert store.get(_key()) == _PAYLOAD


def test_a_missing_file_is_reported_not_returned_empty(tmp_path: Path):
    with pytest.raises(BlobNotFound):
        LocalBlobStore(tmp_path).get(_key())


def test_a_stream_comes_back_in_chunks_and_whole(tmp_path: Path, monkeypatch):
    from backend.workspace_services import blob_store

    monkeypatch.setattr(blob_store, "STREAM_CHUNK_BYTES", 8)
    store = LocalBlobStore(tmp_path)
    store.put(_key(), _PAYLOAD, content_hash=_HASH)

    chunks = list(store.stream(_key()))

    assert len(chunks) > 1
    assert b"".join(chunks) == _PAYLOAD


def test_a_missing_file_fails_before_the_stream_starts(tmp_path: Path):
    with pytest.raises(BlobNotFound):
        LocalBlobStore(tmp_path).stream(_key())


def test_deleting_twice_is_not_an_error(tmp_path: Path):
    store = LocalBlobStore(tmp_path)
    store.put(_key(), _PAYLOAD, content_hash=_HASH)

    store.delete(_key())
    store.delete(_key())

    with pytest.raises(BlobNotFound):
        store.get(_key())


@pytest.mark.parametrize("key", ["", "../segreti.txt", "source_uploads/../../fuori.txt", "altro/file.txt"])
def test_a_key_outside_the_sources_is_refused(tmp_path: Path, key: str):
    with pytest.raises(BlobKeyError):
        LocalBlobStore(tmp_path).get(key)


def test_keys_are_per_tenant_and_do_not_show_the_tenant(tmp_path: Path):
    a = source_key("tenant-a", _HASH, ".txt")
    b = source_key("tenant-b", _HASH, ".txt")

    assert a != b
    assert "tenant-a" not in a
    assert a.startswith("source_uploads/") and a.endswith(f"{_HASH}.txt")


def test_the_default_root_does_not_depend_on_the_working_directory(monkeypatch, tmp_path: Path):
    from backend.settings import settings

    monkeypatch.setattr(settings, "source_storage_root", None)
    monkeypatch.chdir(tmp_path)

    root = storage_root()

    assert root.is_absolute()
    assert tmp_path not in root.parents
    assert root.name == "data"


def test_the_root_can_be_configured(monkeypatch, tmp_path: Path):
    from backend.settings import settings

    monkeypatch.setattr(settings, "source_storage_root", str(tmp_path / "archivio"))

    assert storage_root() == tmp_path / "archivio"


def test_a_relative_root_is_read_from_the_project_not_the_working_directory(monkeypatch, tmp_path: Path):
    from backend.settings import settings

    monkeypatch.setattr(settings, "source_storage_root", "archivio")
    monkeypatch.chdir(tmp_path)

    root = storage_root()

    assert root.is_absolute()
    assert tmp_path not in root.parents
    assert root.name == "archivio"
