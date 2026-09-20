"""Prepara un worktree pronto per lavorare, in un comando.

    uv run python scripts/new_agent_worktree.py <nome> [--branch <branch>] [--base main]

Perche' esiste. Un worktree appena creato in questo repo **non gira**: `.env` e'
gitignorato, quindi nasce senza, e senza `WORKSPACE_DATABASE_URL` ogni test va in
errore (non skip) al fixture di sessione. Poi, anche con `.env`, due sessioni che
condividono il database `workspace` si chiudono fuori a vicenda: basta che una
applichi una migrazione che l'altra non ha, e l'altra trova

    alembic.script.revision.ResolutionError: No such revision or branch '00xx_...'

su **tutti** i test. Non e' un bug del codice, e sembra un bug del codice. E' il
motivo per cui questo script esiste: ogni sessione ha il suo database.

Cosa fa, in ordine:

1. crea il worktree e il branch dalla base indicata;
2. copia `.env` e `ops/.env` dal checkout principale;
3. allinea le DSN alla porta su cui Postgres gira **adesso** (su questa macchina
   cambia: 55432 cade in un intervallo TCP riservato da Windows);
4. crea il database `workspace_<nome>` e ci punta `WORKSPACE_DATABASE_URL`;
5. lo porta a head con Alembic;
6. stampa cosa fare dopo.

Non tocca `canonical` ne' `mem0`: sono condivisi, e al momento in cui questo
script e' stato scritto erano allineati. Se un domani anche quelli driftano, la
cura e' la stessa.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

# La console Windows parla cp1252: un carattere fuori da quella tabella fa
# morire lo script sull'ultima `print`, dopo che il lavoro e' gia' stato fatto -
# il modo piu' fastidioso di rompersi. Qui si resta in ASCII, e per sicurezza si
# chiede a stdout di non lamentarsi.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

WORKTREE_ROOT = Path(".claude/worktrees")
PG_CONTAINER = "delir-postgres"
SUPERUSER = "delir_super"
NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,40}$")


class SetupError(RuntimeError):
    """Un passo non e' riuscito, e continuare lascerebbe un worktree a metà."""


def run(command: list[str], *, cwd: Path | None = None, check: bool = True) -> str:
    result = subprocess.run(
        command, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if check and result.returncode != 0:
        raise SetupError(
            f"comando fallito ({result.returncode}): {' '.join(command)}\n"
            f"{(result.stderr or result.stdout).strip()}"
        )
    return (result.stdout or "").strip()


def main_checkout() -> Path:
    """Il checkout principale: la prima riga di `git worktree list`."""
    first = run(["git", "worktree", "list", "--porcelain"]).splitlines()[0]
    return Path(first.removeprefix("worktree ").strip())


def live_postgres_port() -> str | None:
    """La porta su cui Postgres e' pubblicato adesso, letta dal container.

    Si legge invece di assumerla perche' su questa macchina cambia: due sessioni
    che fanno `docker compose up` si ricreano il container a vicenda, e l'ultima
    decide la porta.
    """
    ports = run(
        ["docker", "ps", "--filter", f"name={PG_CONTAINER}", "--format", "{{.Ports}}"],
        check=False,
    )
    match = re.search(r"127\.0\.0\.1:(\d+)->5432/tcp", ports)
    return match.group(1) if match else None


def align_dsn_port(env_path: Path, port: str) -> int:
    """Riscrive le porte delle DSN Postgres nel `.env`. Torna quante ha cambiate."""
    text = env_path.read_text(encoding="utf-8")
    updated, changes = re.subn(r"(127\.0\.0\.1):\d+(/)", rf"\g<1>:{port}\g<2>", text)
    if changes:
        env_path.write_text(updated, encoding="utf-8")
    return changes


def point_workspace_database(env_path: Path, database: str) -> None:
    """Fa puntare `WORKSPACE_DATABASE_URL` al database di questo worktree."""
    text = env_path.read_text(encoding="utf-8")
    pattern = re.compile(r"^(WORKSPACE_DATABASE_URL=.*/)([A-Za-z0-9_]+)\s*$", re.MULTILINE)
    if not pattern.search(text):
        raise SetupError(
            f"{env_path} non contiene una WORKSPACE_DATABASE_URL riconoscibile: "
            "impostala a mano e rilancia"
        )
    env_path.write_text(pattern.sub(rf"\g<1>{database}", text), encoding="utf-8")


def create_database(database: str) -> str:
    """Crea il database, se non c'e' gia'. Idempotente."""
    exists = run(
        [
            "docker", "exec", PG_CONTAINER, "psql", "-U", SUPERUSER, "-d", "delir",
            "-tAc", f"SELECT 1 FROM pg_database WHERE datname='{database}'",
        ],
        check=False,
    )
    if exists.strip() == "1":
        return "esisteva gia'"
    run(
        [
            "docker", "exec", PG_CONTAINER, "psql", "-U", SUPERUSER, "-d", "delir",
            "-c", f"CREATE DATABASE {database} OWNER delir_workspace;",
        ]
    )
    return "creato"


def copy_env_files(source: Path, target: Path) -> list[str]:
    copied = []
    for relative in (Path(".env"), Path("ops/.env")):
        origin = source / relative
        if not origin.exists():
            raise SetupError(
                f"manca {origin}. Serve il checkout principale configurato: "
                "questi file sono gitignorati e non esistono in un clone pulito."
            )
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origin, destination)
        copied.append(str(relative))
    return copied


def setup(name: str, *, branch: str, base: str) -> Path:
    if not NAME_PATTERN.fullmatch(name):
        raise SetupError(
            f"nome non valido: {name!r}. Minuscole, cifre, `-` e `_`, max 41 caratteri: "
            "diventa anche il nome di un database."
        )

    root = main_checkout()
    worktree = root / WORKTREE_ROOT / name
    database = f"workspace_{name.replace('-', '_')}"

    if worktree.exists():
        raise SetupError(f"{worktree} esiste gia'. Scegli un altro nome, o rimuovilo.")

    print(f"[1/6] worktree {worktree.relative_to(root)} su {branch} (da {base})")
    run(["git", "worktree", "add", str(worktree), "-b", branch, base], cwd=root)

    print("[2/6] copio .env e ops/.env dal checkout principale")
    for relative in copy_env_files(root, worktree):
        print(f"       {relative}")

    print("[3/6] allineo la porta di Postgres")
    port = live_postgres_port()
    if port is None:
        print(
            f"       ATTENZIONE: il container {PG_CONTAINER} non risulta attivo. "
            "Le DSN restano come sono; avvia lo stack e rilancia il passo 3-5 a mano."
        )
    else:
        changed = align_dsn_port(worktree / ".env", port)
        print(f"       porta {port}, {changed} DSN aggiornate")

    print(f"[4/6] database {database}")
    print(f"       {create_database(database)}")

    print("[5/6] punto WORKSPACE_DATABASE_URL al database di questo worktree")
    point_workspace_database(worktree / ".env", database)

    print("[6/6] porto lo schema a head")
    run(["uv", "run", "alembic", "-c", "alembic_workspace.ini", "upgrade", "head"], cwd=worktree)

    return worktree


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prepara un worktree isolato, con il suo database, pronto per i test."
    )
    parser.add_argument("name", help="nome breve: diventa cartella, branch e database")
    parser.add_argument("--branch", help="nome del branch (default: chore/<nome>)")
    parser.add_argument("--base", default="main", help="da dove partire (default: main)")
    args = parser.parse_args(argv)

    branch = args.branch or f"chore/{args.name}"

    try:
        worktree = setup(args.name, branch=branch, base=args.base)
    except SetupError as error:
        print(f"\nERRORE: {error}", file=sys.stderr)
        return 1

    print(
        f"\nPronto: {worktree}\n"
        f"  cd {worktree}\n"
        "  uv run pytest -q                      # la suite gira, isolata\n"
        "\nDue cose da sapere:\n"
        "  - i test non chiamano il modello vero. Chi deve spendere si marca\n"
        "    `live_llm` e gira con DELIR_LIVE_LLM=1 (vedi tests/live_llm.py).\n"
        "  - `npm ci --legacy-peer-deps` dentro frontend/ solo se tocchi il frontend:\n"
        "    node_modules non si eredita dal checkout principale.\n"
        "\nLo stato dei lavori sulla spesa LLM e' in docs/llm-spend-status.md:\n"
        "  la sezione 2 dice il prossimo passo, la 5 le trappole d'ambiente."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
