"""Ispezione e requeue delle code di proiezione (canonical -> Neo4j / Mem0).

Gira come `delir_migrator` (`CANONICAL_MIGRATOR_URL`): il requeue tocca
`attempts` / `last_error`, che il worker non puo' azzerare da solo.

    CANONICAL_MIGRATOR_URL=... uv run python -m scripts.queue_admin list
    CANONICAL_MIGRATOR_URL=... uv run python -m scripts.queue_admin show <id> [--queue mem0_projection_log]
    CANONICAL_MIGRATOR_URL=... uv run python -m scripts.queue_admin requeue-stuck [--queue ...]
    CANONICAL_MIGRATOR_URL=... uv run python -m scripts.queue_admin purge-invalid [--apply]

`purge-invalid` sposta in `graph_outbox_dead_letter` le righe mai processate il
cui payload non e' applicabile (nessun `kind` fra quelli noti). Il CHECK della
0017 impedisce che ne entrino di nuove, ma quelle gia' in coda restano: sono
veleni, e riprovarle non le rende valide. Il worker le sposta da solo quando le
incontra; questo comando serve per farlo in blocco, senza aspettare che la coda
ci ripassi. Senza `--apply` elenca soltanto.
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
                f"       count(*) FILTER (WHERE {done_col} IS NULL AND attempts < 5 "
                f"                          AND next_attempt_at > now()) AS waiting, "
                f"       count(*) FILTER (WHERE {done_col} IS NULL AND attempts >= 5) AS stuck, "
                f"       count(*) FILTER (WHERE {done_col} IS NOT NULL) AS done "
                f"FROM {queue}"
            )
        ).one()
        print(
            f"{queue:22} pending={row.pending:<6} (in attesa di backoff: {row.waiting}) "
            f"stuck={row.stuck:<6} done={row.done}"
        )
    dead = conn.execute(text("SELECT count(*) FROM graph_outbox_dead_letter")).scalar()
    print(f"{'graph_outbox_dead_letter':22} righe messe da parte={dead}")


def cmd_show(conn, queue: str, row_id: int) -> None:
    done_col = _QUEUES[queue]
    row = conn.execute(
        text(
            f"SELECT id, aggregate_type, attempts, throttled_count, next_attempt_at, "
            f"       {done_col} AS done_at, last_error, payload "
            f"FROM {queue} WHERE id = :i"
        )
        if queue == "graph_outbox"
        else text(
            f"SELECT id, memory_kind AS aggregate_type, attempts, throttled_count, "
            f"       next_attempt_at, {done_col} AS done_at, "
            f"last_error, mem0_payload AS payload FROM {queue} WHERE id = :i"
        ),
        {"i": row_id},
    ).first()
    if row is None:
        print("riga non trovata")
        return
    print(
        f"id={row.id} type={row.aggregate_type} attempts={row.attempts} "
        f"throttled={row.throttled_count} next_attempt_at={row.next_attempt_at} "
        f"done_at={row.done_at}"
    )
    print(f"last_error: {row.last_error}")
    print(f"payload: {row.payload}")


_INVALID_PAYLOAD = (
    "processed_at IS NULL AND COALESCE(payload->>'kind', '') NOT IN "
    "('node','edge','node_delete','edge_delete')"
)


def cmd_requeue_stuck(conn, queue: str) -> None:
    done_col = _QUEUES[queue]
    # Un payload non applicabile non torna in coda: rimetterlo significa solo
    # rifargli consumare gli stessi tentativi per lo stesso motivo. Si toglie
    # con `purge-invalid`, che e' una decisione, non un automatismo.
    skip_poison = f" AND NOT ({_INVALID_PAYLOAD})" if queue == "graph_outbox" else ""
    n = conn.execute(
        text(
            f"UPDATE {queue} SET attempts = 0, throttled_count = 0, "
            f"    last_error = NULL, next_attempt_at = now() "
            f"WHERE {done_col} IS NULL AND attempts >= 5{skip_poison}"
        )
    ).rowcount
    print(f"{queue}: {n} righe rimesse in coda")
    if skip_poison:
        left = conn.execute(
            text(f"SELECT count(*) FROM {queue} WHERE attempts >= 5 AND ({_INVALID_PAYLOAD})")
        ).scalar()
        if left:
            print(f"{queue}: {left} righe con payload non applicabile lasciate ferme (purge-invalid)")


def cmd_purge_invalid(conn, apply: bool) -> None:
    rows = conn.execute(
        text(
            "SELECT id, aggregate_type, dedupe_key, created_at, left(payload::text, 80) AS payload "
            f"FROM graph_outbox WHERE {_INVALID_PAYLOAD} ORDER BY id"
        )
    ).all()
    if not rows:
        print("graph_outbox: nessuna riga con payload non applicabile")
        return
    for row in rows[:20]:
        print(f"  id={row.id} type={row.aggregate_type} dedupe_key={row.dedupe_key} payload={row.payload}")
    if len(rows) > 20:
        print(f"  ... e altre {len(rows) - 20}")
    if not apply:
        print(f"graph_outbox: {len(rows)} righe da spostare nel dead-letter (dry-run, usa --apply)")
        return
    # Spostate, non cancellate: il payload resta leggibile per capire chi l'ha
    # prodotto. Cancellarlo toglierebbe l'unica prova di come ci e' finito.
    conn.execute(
        text(
            "INSERT INTO graph_outbox_dead_letter "
            "(id, aggregate_type, aggregate_id, consultant_id, client_id, op, payload, "
            " dedupe_key, created_at, attempts, last_error, reason) "
            "SELECT id, aggregate_type, aggregate_id, consultant_id, client_id, op, payload, "
            "       dedupe_key, created_at, attempts, last_error, "
            "       'payload non applicabile (queue_admin purge-invalid)' "
            f"FROM graph_outbox WHERE {_INVALID_PAYLOAD} "
            "ON CONFLICT (id) DO NOTHING"
        )
    )
    moved = conn.execute(text(f"DELETE FROM graph_outbox WHERE {_INVALID_PAYLOAD}")).rowcount
    print(f"graph_outbox: {moved} righe spostate in graph_outbox_dead_letter")


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    p_show = sub.add_parser("show")
    p_show.add_argument("id", type=int)
    p_show.add_argument("--queue", default="graph_outbox", choices=list(_QUEUES))
    p_rq = sub.add_parser("requeue-stuck")
    p_rq.add_argument("--queue", default="graph_outbox", choices=list(_QUEUES))
    p_pi = sub.add_parser("purge-invalid")
    p_pi.add_argument("--apply", action="store_true", help="senza, elenca soltanto")
    args = parser.parse_args()

    with _engine().begin() as conn:
        if args.cmd == "list":
            cmd_list(conn)
        elif args.cmd == "show":
            cmd_show(conn, args.queue, args.id)
        elif args.cmd == "requeue-stuck":
            cmd_requeue_stuck(conn, args.queue)
        elif args.cmd == "purge-invalid":
            cmd_purge_invalid(conn, args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
