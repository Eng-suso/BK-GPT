"""Gli attrezzi che ogni aggregato del workspace usa: liste e milestone
serializzate, ora, tenant, id e slug.
"""

import json
import re
from datetime import UTC, datetime
from typing import TypeVar

from sqlalchemy.orm import Session

from backend.security import get_current_tenant_id
from backend.workspace_milestones import normalise_milestones
from backend.workspace_storage import WorkspaceBase


def encode_list(values: list[str]) -> str:
    return json.dumps(values, ensure_ascii=False)


def decode_list(value: str) -> list[str]:
    parsed = json.loads(value or "[]")
    return parsed if isinstance(parsed, list) else []


def decode_milestones(value: str) -> list[dict]:
    """Read the stored milestones, upgrading rows written as plain titles.

    Args:
        value: The project's stored ``milestones_json`` payload.

    Returns:
        list[dict]: The milestones as ``{title, status, completed_at}``.
    """
    return normalise_milestones(decode_list(value))


def encode_milestones(values: list[dict]) -> str:
    return json.dumps(values, ensure_ascii=False)


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def tenant_id() -> str:
    return get_current_tenant_id()


_Row = TypeVar("_Row", bound=WorkspaceBase)


def tenant_row(session: Session, model: type[_Row], row_id: str) -> _Row | None:
    row = session.get(model, row_id)
    if row is None or getattr(row, "tenant_id", "local") != tenant_id():
        return None
    return row


def slugify(value: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or fallback


def normalize_name(value: str) -> str:
    return " ".join(value.casefold().split())


def unique_id(session: Session, model: type[WorkspaceBase], base_id: str) -> str:
    candidate = base_id
    suffix = 2

    while session.get(model, candidate) is not None:
        candidate = f"{base_id}-{suffix}"
        suffix += 1

    return candidate
