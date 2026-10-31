"""Le regole del deploy di produzione, controllate a ogni modifica del compose.

La VM e' una sola (Oracle A1, 2 OCPU / 12 GB garantiti): un limite di memoria
alzato per sbaglio, o una porta pubblicata su 0.0.0.0, non si vedono finche'
la macchina non va in OOM o qualcuno non entra. Qui si vedono prima del merge.
"""
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "ops" / "docker-compose.yml"
PROD = ROOT / "ops" / "docker-compose.prod.yml"

#: 12 GB della VM meno ~1 GB per il sistema e cloudflared.
MEMORY_BUDGET_BYTES = 11 * 1024**3

_UNITS = {"k": 1024, "m": 1024**2, "g": 1024**3}


def _bytes(value: str) -> int:
    match = re.fullmatch(r"(\d+)([kmg])b?", str(value).strip().lower())
    assert match, f"limite di memoria illeggibile: {value!r}"
    return int(match.group(1)) * _UNITS[match.group(2)]


def _merged_services() -> dict[str, dict]:
    base = yaml.safe_load(BASE.read_text(encoding="utf-8"))["services"]
    prod = yaml.safe_load(PROD.read_text(encoding="utf-8"))["services"]
    return {name: {**base.get(name, {}), **prod.get(name, {})} for name in base.keys() | prod.keys()}


def _memory_limit(service: dict) -> str | None:
    return service.get("deploy", {}).get("resources", {}).get("limits", {}).get("memory")


def test_every_service_has_a_memory_limit():
    """Senza limite, un servizio affamato (Docling su un PDF grosso) si prende la VM."""
    missing = sorted(name for name, service in _merged_services().items() if not _memory_limit(service))
    assert missing == []


def test_the_whole_stack_fits_in_the_vm():
    total = sum(_bytes(_memory_limit(service)) for service in _merged_services().values())
    assert total <= MEMORY_BUDGET_BYTES, f"{total / 1024**3:.1f} GB su {MEMORY_BUDGET_BYTES / 1024**3:.0f}"


@pytest.mark.parametrize("name", ["postgres", "neo4j", "docling", "prosimos", "app"])
def test_no_service_is_reachable_from_outside_the_vm(name: str):
    """Il traffico entra dal tunnel; una porta su 0.0.0.0 scavalca tutto."""
    for port in _merged_services()[name].get("ports", []):
        assert str(port).startswith("127.0.0.1:"), f"{name} pubblica {port}"


def test_in_production_the_app_does_not_migrate_by_itself():
    """Lo schema lo porta a head l'entrypoint, sotto lock (scripts/migrate.py)."""
    environment = _merged_services()["app"]["environment"]
    assert environment["RUN_MIGRATIONS_ON_STARTUP"] == "false"
    assert environment["DELIR_ENVIRONMENT"] == "prod"
    assert environment["DELIR_AUTH_ENABLED"] == "true"


def test_the_app_runs_a_single_process():
    """I lock dei turni di chat stanno in memoria di processo (fragilita-status B4)."""
    entrypoint = (ROOT / "ops" / "docker" / "entrypoint.sh").read_text(encoding="utf-8")
    assert re.search(r"--workers 1\b", entrypoint)


def test_the_image_carries_no_secrets():
    ignored = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    assert "**/.env" in ignored
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert not re.search(r"(?i)(api_key|token|password)\s*=", dockerfile)
