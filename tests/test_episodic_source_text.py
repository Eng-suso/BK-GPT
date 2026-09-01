"""`read_source_text` preferisce il testo dal DB (`content`) alla cache su disco."""

from __future__ import annotations

from backend.settings import settings

if not settings.workspace_database_url:  # l'import di episodic_store richiede la DSN
    import pytest

    pytest.skip("serve WORKSPACE_DATABASE_URL", allow_module_level=True)

from backend.memory.episodic.episodic_store import (  # noqa: E402
    EpisodeSource,
    episode_to_dict,
    read_source_text,
)


def test_prefers_db_content():
    src = {"content": "testo dal database", "path": "/non/esiste.md"}
    assert read_source_text(src) == "testo dal database"


def test_read_from_orm_source():
    src = EpisodeSource(
        source_id="s1", episode_id="e1", source_type="note", title="t",
        path="/manca.md", content="dal DB via ORM", origin="chat",
        content_hash="h", created_at="2026-01-01",
    )
    assert read_source_text(src) == "dal DB via ORM"


def test_episode_to_dict_omits_content():
    # `content` puo' essere un transcript intero: non deve finire nelle liste
    src = EpisodeSource(
        source_id="s1", episode_id="e1", source_type="note", title="t",
        path="/x.md", content="x" * 10000, origin="chat",
        content_hash="h", created_at="2026-01-01",
    )
    from backend.memory.episodic.episodic_store import Episode

    ep = Episode(
        episode_id="e1", episode_type="note", title="t", participants="[]",
        insights="[]", tags="[]", status="active", created_at="2026-01-01",
        updated_at="2026-01-01",
    )
    d = episode_to_dict(ep, src)
    assert "content" not in d
    assert d["path"] == "/x.md"


def test_falls_back_to_disk_when_no_content(tmp_path):
    f = tmp_path / "s.md"
    f.write_text("testo dal disco", encoding="utf-8")
    assert read_source_text({"content": None, "path": str(f)}) == "testo dal disco"


def test_empty_when_neither():
    assert read_source_text({"content": None, "path": "/manca.md"}) == ""
    assert read_source_text({}) == ""
