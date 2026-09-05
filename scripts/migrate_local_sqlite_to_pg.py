"""Copia lo stato operativo dai file SQLite locali al database `workspace` Postgres.

One-shot. Legge i file SQLite legacy in `data/_legacy_sqlite/` (`workspace.db`,
`chat_history.db`, `episodic_memory.db`) e inserisce le righe nel Postgres
puntato da `WORKSPACE_DATABASE_URL` (che deve essere configurata).

Le tabelle di destinazione le crea l'app all'import (`create_all`); questo
script assume che esistano gia' e siano vuote (o passa `--truncate`).

    WORKSPACE_DATABASE_URL=postgresql+psycopg://delir_workspace:...@host/workspace \
      uv run python -m scripts.migrate_local_sqlite_to_pg [--truncate] [--dry-run]

Insert riga-per-riga con savepoint: una riga corrotta viene saltata, non fa
fallire la tabella. Sequenze PK autoincrement riallineate a fine copia.

Il testo grezzo degli episodi (vecchi file `data/episodic/sources/*.md`) viene
letto e messo in `sources.content`: dopo la migrazione l'host non dipende piu'
da quei file.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from backend.settings import settings

DATA = Path("data") / "_legacy_sqlite"

# (file sqlite, tabelle in ordine di dipendenza FK, colonne id autoincrement)
PLAN = [
    (
        DATA / "workspace.db",
        [
            "workspace_clients",
            "workspace_projects",
            "workspace_processes",
            "workspace_bpmn_models",
            "workspace_bpmn_versions",
            "workspace_bpmn_reviews",
            "workspace_simulation_runs",
            "workspace_simulation_run_artifacts",
            "workspace_sources",
            "workspace_decisions",
        ],
        {"workspace_bpmn_versions": "id", "workspace_simulation_runs": "id"},
    ),
    (
        DATA / "chat_history.db",
        ["chat_sessions", "chat_messages"],
        {"chat_messages": "id"},
    ),
    (
        DATA / "episodic_memory.db",
        ["episodes", "sources"],
        {},
    ),
]


def _copy_table(src: Engine, dst: Engine, table: str, dry_run: bool) -> tuple[int, int]:
    """Ritorna (righe inserite, righe saltate). Insert riga-per-riga con
    savepoint: una riga corrotta (FK orfana, tipo strano) viene saltata, non
    fa fallire tutta la tabella."""
    with src.connect() as sconn:
        if table not in _table_names(src):
            return 0, 0
        rows = [dict(r) for r in sconn.execute(text(f"SELECT * FROM {table}")).mappings()]
    if not rows or dry_run:
        return len(rows), 0

    cols = list(rows[0].keys())
    placeholders = ", ".join(f":{c}" for c in cols)
    stmt = text(
        f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT DO NOTHING"
    )
    inserted = skipped = 0
    with dst.begin() as dconn:
        for row in rows:
            sp = dconn.begin_nested()
            try:
                dconn.execute(stmt, row)
                sp.commit()
                inserted += 1
            except Exception as exc:  # noqa: BLE001
                sp.rollback()
                skipped += 1
                print(f"    ! {table}: riga saltata ({exc})")
    return inserted, skipped


def _backfill_episode_content(dst: Engine, dry_run: bool) -> int:
    """Riempie `sources.content` leggendo i file `.md` su disco (`path`), cosi'
    gli episodi vecchi non dipendono piu' dalla custodia su disco."""
    if dry_run:
        return 0
    filled = 0
    with dst.begin() as conn:
        pending = conn.execute(
            text("SELECT source_id, path FROM sources WHERE content IS NULL AND path <> ''")
        ).all()
        for source_id, path in pending:
            try:
                text_value = Path(path).read_text(encoding="utf-8")
            except OSError:
                continue
            conn.execute(
                text("UPDATE sources SET content = :c WHERE source_id = :i"),
                {"c": text_value, "i": source_id},
            )
            filled += 1
    return filled


def _table_names(engine: Engine) -> set[str]:
    with engine.connect() as conn:
        return {
            r[0]
            for r in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )
        }


def _reset_sequence(dst: Engine, table: str, id_col: str) -> None:
    with dst.begin() as conn:
        conn.execute(
            text(
                f"SELECT setval(pg_get_serial_sequence('{table}', '{id_col}'), "
                f"COALESCE((SELECT MAX({id_col}) FROM {table}), 1))"
            )
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--truncate", action="store_true", help="svuota le tabelle di destinazione prima")
    parser.add_argument("--dry-run", action="store_true", help="conta soltanto, non scrive")
    args = parser.parse_args()

    if not settings.workspace_database_url:
        print("WORKSPACE_DATABASE_URL non configurata", file=sys.stderr)
        return 2

    dst = create_engine(settings.workspace_database_url, future=True)

    # lo schema di destinazione lo porta a head Alembic (migrations_workspace)
    from backend.local_store import ensure_schema

    ensure_schema.cache_clear()
    ensure_schema()

    total = skipped_total = 0
    for sqlite_path, tables, id_cols in PLAN:
        if not sqlite_path.exists():
            print(f"skip {sqlite_path} (assente)")
            continue
        src = create_engine(f"sqlite:///{sqlite_path.as_posix()}", future=True)

        if args.truncate and not args.dry_run:
            with dst.begin() as conn:
                for table in reversed(tables):
                    conn.execute(text(f"TRUNCATE {table} CASCADE"))

        for table in tables:
            n, skipped = _copy_table(src, dst, table, args.dry_run)
            total += n
            skipped_total += skipped
            print(f"  {table}: {n}" + (f" ({skipped} saltate)" if skipped else ""))

        for table, id_col in id_cols.items():
            if not args.dry_run:
                _reset_sequence(dst, table, id_col)

    filled = _backfill_episode_content(dst, args.dry_run)
    if filled:
        print(f"  sources.content: {filled} riempite da disco")

    tag = "(dry-run) " if args.dry_run else ""
    print(f"{tag}righe totali: {total}" + (f", saltate: {skipped_total}" if skipped_total else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
