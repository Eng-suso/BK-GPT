"""Ispezione e requeue delle code di proiezione (canonical -> Neo4j / Mem0).

Gira come `delir_migrator` (`CANONICAL_MIGRATOR_URL`): il requeue tocca
`attempts` / `last_error`, che il worker non puo' azzerare da solo.

    CANONICAL_MIGRATOR_URL=... uv run python -m scripts.queue_admin list
    CANONICAL_MIGRATOR_URL=... uv run python -m scripts.queue_admin show <id> [--queue mem0_projection_log]
    CANONICAL_MIGRATOR_URL=... uv run python -m scripts.queue_admin requeue-stuck [--queue ...]
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import create_engine, text

from backend.settings import settings

_QUEUES = {
    "graph_outbox": "processed_at",
    "mem0_projection_log": "applied_at",
}


def _engine():
    if not settings.canonical_migrator_url:
        print("CANONICAL_MIGRATOR_URL non configurata", file=sys.stderr)
        raise SystemExit(2)
    return create_engine(settings.canonical_migrator_url, future=True)


def cmd_list(conn) -> None:
    for queue, done_col in _QUEUES.items():
        row = conn.execute(
            text(
                f"SELECT count(*) FILTER (WHERE {done_col} IS NULL AND attempts < 5) AS pending, "
                f"       count(*) FILTER (WHERE {done_col} IS NULL AND attempts >= 5) AS stuck, "
                f"       count(*) FILTER (WHERE {done_col} IS NOT NULL) AS done "
                f"FROM {queue}"
            )
        ).one()
        print(f"{queue:22} pending={row.pending:<6} stuck={row.stuck:<6} done={row.done}")


def cmd_show(conn, queue: str, row_id: int) -> None:
    done_col = _QUEUES[queue]
    row = conn.execute(
        text(
            f"SELECT id, aggregate_type, attempts, {done_col} AS done_at, last_error, payload "
            f"FROM {queue} WHERE id = :i"
        )
        if queue == "graph_outbox"
        else text(
            f"SELECT id, memory_kind AS aggregate_type, attempts, {done_col} AS done_at, "
            f"last_error, mem0_payload AS payload FROM {queue} WHERE id = :i"
        ),
        {"i": row_id},
    ).first()
    if row is None:
        print("riga non trovata")
        return
    print(f"id={row.id} type={row.aggregate_type} attempts={row.attempts} done_at={row.done_at}")
    print(f"last_error: {row.last_error}")
    print(f"payload: {row.payload}")


def cmd_requeue_stuck(conn, queue: str) -> None:
    done_col = _QUEUES[queue]
    n = conn.execute(
        text(
            f"UPDATE {queue} SET attempts = 0, last_error = NULL "
            f"WHERE {done_col} IS NULL AND attempts >= 5"
        )
    ).rowcount
    print(f"{queue}: {n} righe rimesse in coda")


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    p_show = sub.add_parser("show")
    p_show.add_argument("id", type=int)
    p_show.add_argument("--queue", default="graph_outbox", choices=list(_QUEUES))
    p_rq = sub.add_parser("requeue-stuck")
    p_rq.add_argument("--queue", default="graph_outbox", choices=list(_QUEUES))
    args = parser.parse_args()

    with _engine().begin() as conn:
        if args.cmd == "list":
            cmd_list(conn)
        elif args.cmd == "show":
            cmd_show(conn, args.queue, args.id)
        elif args.cmd == "requeue-stuck":
            cmd_requeue_stuck(conn, args.queue)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
