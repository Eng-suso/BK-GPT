"""Ispeziona o azzera la memoria consulente, per avere una baseline pulita.

Serve dopo un giro di test end-to-end: il consultant store si sporca (memorie
seminate dai test, fatti riscritti da Mem0, id incoerenti) e da quel momento
ogni difetto osservato in chat e' ambiguo — memoria del consulente o bug del
progetto? Questo script chiude l'ambiguita' partendo da zero.

    uv run python -m scripts.memory_baseline inspect
    uv run python -m scripts.memory_baseline reset --yes
    uv run python -m scripts.memory_baseline reset --yes --user-id test-marco

`inspect` non tocca nulla: elenca cosa c'e' in Mem0 per lo user_id corrente e
quante righe canonical/tombstone/pending esistono per il consulente.

`reset` cancella, in quest'ordine: le memorie Mem0 dello user_id, le lapidi, le
azioni in attesa e le righe `semantic_memory` / `episodic_memory`
consultant-scoped. Richiede `--yes`: e' distruttivo e non e' reversibile.
Le evidenze di progetto (kg_source, kg_chunk, workspace) non vengono toccate:
per un cliente si usa `neo4j_store.purge_client` + il flusso di cancellazione
cliente, non questo script.
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import text

from backend.memory import mem0_client
from backend.memory.mem0_client import Mem0Disabled
from backend.settings import settings


def _mem0_items(raw) -> list:
    """
    Normalize a Mem0 response into a list of memory items.
    
    Parameters:
    	raw: A Mem0 response, either as a mapping containing memory items or as an iterable of items.
    
    Returns:
    	list: The memory items extracted from the response, or an empty list when none are present.
    """
    if isinstance(raw, dict):
        return raw.get("results") or raw.get("memories") or []
    return raw or []


def _list_mem0(user_id: str, limit: int = 200) -> list[dict]:
    """
    List Mem0 memories for a user.
    
    Parameters:
    	user_id (str): Identifier of the user whose memories are retrieved.
    	limit (int): Maximum number of memories to retrieve.
    
    Returns:
    	list[dict]: Retrieved memory records, or an empty list when Mem0 is disabled.
    """
    memory = mem0_client.get_memory()
    if isinstance(memory, Mem0Disabled):
        print(f"Mem0 disattivato: {memory.reason}")
        return []
    raw = memory.get_all(filters={"user_id": user_id}, top_k=limit)
    return [item for item in _mem0_items(raw) if isinstance(item, dict)]


def _canonical_counts(consultant_id: str) -> dict[str, int]:
    """Count rows in the canonical memory tables for a consultant.
    
    Parameters:
        consultant_id (str): Identifier of the consultant whose memory rows are counted.
    
    Returns:
        dict[str, int]: Row counts keyed by table name, or an empty dictionary when the canonical database is not configured. A value of -1 indicates that a table could not be queried.
    """
    if not settings.canonical_database_url:
        return {}
    from backend.db import canonical_session

    counts: dict[str, int] = {}
    with canonical_session(consultant_id) as session:
        for table in (
            "semantic_memory",
            "episodic_memory",
            "memory_tombstone",
            "pending_action",
        ):
            try:
                counts[table] = int(
                    session.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
                )
            except Exception as exc:  # noqa: BLE001 — tabella non ancora migrata
                counts[table] = -1
                print(f"  ! {table}: {exc}")
    return counts


def inspect(user_id: str, consultant_id: str) -> int:
    """
    Display Mem0 memories and canonical memory counts for a consultant.
    
    Parameters:
    	user_id (str): Identifier of the Mem0 user whose memories are displayed.
    	consultant_id (str): Identifier used to count consultant-scoped canonical records.
    
    Returns:
    	int: Exit status `0`.
    """
    print(f"Mem0 user_id: {user_id}")
    items = _list_mem0(user_id)
    print(f"memorie Mem0: {len(items)}")
    for item in items:
        memory_id = item.get("id") or item.get("memory_id") or ""
        statement = item.get("memory") or item.get("text") or ""
        print(f"  [{memory_id}] {statement}")

    print(f"\nconsultant_id canonical: {consultant_id}")
    for table, count in _canonical_counts(consultant_id).items():
        print(f"  {table}: {count}")
    return 0


def reset(user_id: str, consultant_id: str) -> int:
    """
    Reset a consultant's Mem0 and canonical memory state.
    
    Parameters:
    	user_id (str): User whose Mem0 memories are removed.
    	consultant_id (str): Consultant whose canonical memory records are removed.
    
    Returns:
    	int: Zero after the reset operation completes.
    """
    memory = mem0_client.get_memory()
    deleted = 0
    if isinstance(memory, Mem0Disabled):
        print(f"Mem0 disattivato ({memory.reason}): salto l'indice.")
    else:
        for item in _list_mem0(user_id, limit=1000):
            memory_id = item.get("id") or item.get("memory_id")
            if not memory_id:
                continue
            try:
                memory.delete(memory_id=memory_id)
                deleted += 1
            except Exception as exc:  # noqa: BLE001
                print(f"  ! delete {memory_id}: {exc}")
        print(f"Mem0: {deleted} memorie eliminate per user_id={user_id}")

    if not settings.canonical_database_url:
        print("canonical non configurato: niente da azzerare su Postgres.")
        return 0

    from backend.db import canonical_session

    with canonical_session(consultant_id) as session:
        for statement in (
            "DELETE FROM memory_tombstone",
            "DELETE FROM pending_action",
            "DELETE FROM semantic_memory WHERE scope = 'consultant'",
            "DELETE FROM episodic_memory WHERE scope = 'consultant'",
        ):
            try:
                result = session.execute(text(statement))
                print(f"  {statement}: {result.rowcount}")
            except Exception as exc:  # noqa: BLE001
                print(f"  ! {statement}: {exc}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """
    Run the requested memory inspection or reset command.
    
    Args:
        argv: Optional command-line arguments. When omitted, arguments are read
            from the process command line.
    
    Returns:
        The command's exit status. Returns 2 when a reset is requested without
        explicit confirmation.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("inspect", "reset"))
    parser.add_argument(
        "--user-id",
        default=settings.mem0_user_id,
        help="Mem0 user_id da ispezionare/azzerare (default: settings.mem0_user_id).",
    )
    parser.add_argument(
        "--consultant-id",
        default=settings.default_consultant_id,
        help="consultant_id canonical (default: settings.default_consultant_id).",
    )
    parser.add_argument(
        "--yes", action="store_true", help="conferma esplicita richiesta da reset."
    )
    args = parser.parse_args(argv)

    if args.command == "inspect":
        return inspect(args.user_id, args.consultant_id)

    if not args.yes:
        print(
            "reset e' distruttivo e irreversibile: cancella le memorie Mem0 dello "
            f"user_id '{args.user_id}' e le righe di memoria consultant-scoped del "
            f"consulente {args.consultant_id}. Ripeti con --yes per procedere."
        )
        return 2
    return reset(args.user_id, args.consultant_id)


if __name__ == "__main__":
    sys.exit(main())
