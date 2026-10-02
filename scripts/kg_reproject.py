"""Ricostruisce la proiezione Neo4j di un cliente dalle tabelle Postgres (GR-01).

    uv run python -m scripts.kg_reproject --client <uuid> [--consultant <uuid>]
    uv run python -m scripts.kg_reproject --client <uuid> --apply
    uv run python -m scripts.kg_reproject --client <uuid> --apply --resolve-dead-letter

Senza `--apply` confronta e basta: esce 1 se il grafo non coincide con Postgres,
cosi' si puo' mettere in un cron o in un job di controllo.

Con `--apply` ripara (via cio' che avanza, poi MERGE di tutto l'atteso) e
ristampa il confronto: esce 1 se dopo la riparazione resta una differenza.

`--resolve-dead-letter`: le righe del dead-letter di quel cliente sono payload
che la coda non sapra' mai applicare. Dopo una ricostruzione dal dominio il buco
che avevano lasciato e' chiuso, e restando in tabella terrebbero acceso per
sempre il segnale `staleness` di `graph_retrieve`. Vengono cancellate SOLO se il
confronto dopo `--apply` e' pulito, e prima vengono elencate con il motivo.

Ruoli. La lettura del dominio passa da `canonical_session` (delir_app, con RLS:
per questo serve il consulente - default `DEFAULT_CONSULTANT_ID`). Il dead-letter
si cancella come `delir_migrator` (`CANONICAL_MIGRATOR_URL`), come in
`scripts/queue_admin.py`. Non far girare questo script con la DSN del worker:
`delir_worker` non legge il dominio, ed e' giusto che resti cosi'.
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import create_engine, text

from backend.memory.knowledge_graph import reproject
from backend.settings import settings

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")


def _print_diff(title: str, d: reproject.GraphDiff) -> None:
    print(f"{title}: {'pulito' if d.clean else 'DIVERSO'}")
    for key, value in d.summary().items():
        print(f"  {key:16} {value}")
    for name in ("missing_nodes", "extra_nodes", "duplicate_nodes", "drifted_nodes"):
        for label, node_id in getattr(d, name)[:5]:
            print(f"    {name}: {label} {node_id}")
    for name in ("missing_edges", "extra_edges", "duplicate_edges", "drifted_edges"):
        for label, source, target in getattr(d, name)[:5]:
            print(f"    {name}: {source[0]} {source[1]} -[{label}]-> {target[0]} {target[1]}")


def _resolve_dead_letter(client_id: str) -> int:
    if not settings.canonical_migrator_url:
        print("CANONICAL_MIGRATOR_URL non configurata: dead-letter lasciato com'e'",
              file=sys.stderr)
        return 0
    engine = create_engine(settings.canonical_migrator_url, future=True)
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                "DELETE FROM graph_outbox_dead_letter WHERE client_id = CAST(:cl AS uuid) "
                "RETURNING id, aggregate_type, aggregate_id, reason"
            ),
            {"cl": client_id},
        ).all()
    for row in rows:
        print(f"  dead-letter {row.id} risolto: {row.aggregate_type} {row.aggregate_id} "
              f"({(row.reason or '')[:120]})")
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--client", required=True)
    parser.add_argument("--consultant", default=settings.default_consultant_id)
    parser.add_argument("--apply", action="store_true", help="senza, confronta soltanto")
    parser.add_argument("--resolve-dead-letter", action="store_true",
                        help="con --apply: cancella il dead-letter del cliente se il grafo e' pulito")
    args = parser.parse_args()
    if not args.consultant:
        print("serve --consultant (o DEFAULT_CONSULTANT_ID)", file=sys.stderr)
        return 2
    if args.resolve_dead_letter and not args.apply:
        print("--resolve-dead-letter ha senso solo con --apply", file=sys.stderr)
        return 2

    if not args.apply:
        d = reproject.diff(args.consultant, args.client)
        _print_diff("confronto", d)
        return 0 if d.clean else 1

    report = reproject.apply(args.consultant, args.client)
    _print_diff("prima", report.before)
    print(f"rimossi {report.deleted_nodes} nodi / {report.deleted_edges} archi, "
          f"riapplicati {report.applied_nodes} nodi / {report.applied_edges} archi")
    _print_diff("dopo", report.after)
    if not report.after.clean:
        return 1
    if args.resolve_dead_letter:
        print(f"dead-letter risolti: {_resolve_dead_letter(args.client)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
