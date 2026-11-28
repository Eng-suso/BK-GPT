"""Il backup si ripristina davvero: lo dice una prova, non un dump finito senza errori.

Gira gli script veri (`ops/backup/backup.sh`, `restore.sh`) sul Postgres dei test,
con una cartella al posto del bucket: dump dei tre database nella stessa
fotografia del conteggio delle righe, cifratura age, ripristino in database
temporanei e confronto tabella per tabella con il manifesto.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import pytest

from backend.settings import settings

ROOT = Path(__file__).resolve().parents[2]
BACKUP = ROOT / "ops" / "backup" / "backup.sh"
RESTORE = ROOT / "ops" / "backup" / "restore.sh"
TOOLS = ("age", "age-keygen", "rclone", "pg_dump", "pg_restore", "psql")

pytestmark = pytest.mark.skipif(
    not settings.canonical_migrator_url or any(shutil.which(t) is None for t in TOOLS),
    reason="servono il Postgres dei test e " + ", ".join(TOOLS),
)


@pytest.fixture()
def env(tmp_path: Path) -> dict[str, str]:
    url = urlparse(settings.canonical_migrator_url.replace("+psycopg", ""))
    subprocess.run(["age-keygen", "-o", str(tmp_path / "key.txt")], check=True, capture_output=True)
    public = next(
        line.split(": ", 1)[1]
        for line in (tmp_path / "key.txt").read_text().splitlines()
        if line.startswith("# public key: ")
    )
    appdata = tmp_path / "appdata" / "fonti"
    appdata.mkdir(parents=True)
    (appdata / "intervista.txt").write_text("La seconda firma ferma la pratica.", encoding="utf-8")
    return {
        **os.environ,
        "PGHOST": url.hostname or "127.0.0.1",
        "PGPORT": str(url.port or 5432),
        # Il superuser del cluster: lo stack dei test usa la stessa password della CI.
        "PGUSER": os.environ.get("BACKUP_TEST_PGUSER", "delir_super"),
        "PGPASSWORD": os.environ.get("BACKUP_TEST_PGPASSWORD", "ci-super"),
        "BACKUP_AGE_RECIPIENT": public,
        "BACKUP_AGE_IDENTITY": str(tmp_path / "key.txt"),
        "BACKUP_REMOTE": str(tmp_path / "bucket"),
        "BACKUP_APPDATA_DIR": str(tmp_path / "appdata"),
        "BACKUP_WORK_DIR": str(tmp_path / "work"),
        "BACKUP_STATUS_FILE": str(tmp_path / "status.json"),
        "RCLONE_CONFIG": "/dev/null",
    }


def _run(script: Path, *args: str, env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run([str(script), *args], env=env, capture_output=True, text=True, timeout=600)


def test_a_backup_restores_with_every_row_of_every_table(env):
    made = _run(BACKUP, env=env)
    assert made.returncode == 0, made.stderr
    archive = Path(env["BACKUP_REMOTE"]) / made.stdout.strip().splitlines()[-1]
    assert archive.exists()
    # Cifrato: nel file non c'e' traccia del contenuto.
    assert b"seconda firma" not in archive.read_bytes()
    assert '"status": "ok"' in Path(env["BACKUP_STATUS_FILE"]).read_text()

    checked = _run(RESTORE, "--check", "latest", env=env)

    assert checked.returncode == 0, checked.stderr
    assert "PROVA RIUSCITA" in checked.stderr
    for db in ("delir", "workspace", "mem0"):
        assert f"{db}: " in checked.stderr and "tutte uguali" in checked.stderr


def test_a_tampered_backup_is_refused(env):
    made = _run(BACKUP, env=env)
    archive = Path(env["BACKUP_REMOTE"]) / made.stdout.strip().splitlines()[-1]
    data = bytearray(archive.read_bytes())
    data[len(data) // 2] ^= 0xFF
    archive.write_bytes(bytes(data))

    assert _run(RESTORE, "--check", str(archive), env=env).returncode != 0


def test_restoring_over_the_live_databases_needs_an_explicit_yes(env):
    refused = _run(RESTORE, "--live", "latest", env=env)

    assert refused.returncode == 2
    assert "--yes" in refused.stderr
