"""`read_source_text` preferisce il testo dal DB (`content`) alla cache su disco."""

from __future__ import annotations

from backend.settings import settings

if not settings.workspace_database_url:  # l'import di episodic_store richiede la DSN
    import pytest

    pytest.skip("serve WORKSPACE_DATABASE_URL", allow_module_level=True)

from backend.memory.episodic.episodic_store import read_source_text  # noqa: E402


def test_prefers_db_content():
    src = {"content": "testo dal database", "path": "/non/esiste.md"}
    assert read_source_text(src) == "testo dal database"


def test_falls_back_to_disk_when_no_content(tmp_path):
    f = tmp_path / "s.md"
    f.write_text("testo dal disco", encoding="utf-8")
    assert read_source_text({"content": None, "path": str(f)}) == "testo dal disco"


def test_empty_when_neither():
    assert read_source_text({"content": None, "path": "/manca.md"}) == ""
    assert read_source_text({}) == ""
