"""Contatori in-process delle degradazioni silenziose (review G6 / G8).

Le letture del gateway (`graph_retrieve` / `memory_search` / `procedural_retrieve`)
e il mirror KG (`mirror_evidence`) sono best-effort: su errore ritornano un
risultato vuoto/`mirrored: False` invece di sollevare. Senza un segnale, il
"cervello" puo' smettere di rispondere o di apprendere per giorni in silenzio.

Questi contatori rendono la degradazione osservabile: incrementati sul path di
fallback, esposti da `GET /v1/observability/degradation`. Non sostituiscono un
sistema di metriche vero — sono un canary a costo zero.
"""

from __future__ import annotations

import logging
import threading
from collections import Counter

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_counts: Counter[str] = Counter()


def bump(component: str, outcome: str, *, detail: str | None = None) -> None:
    """Registra una degradazione. `component` es. "graph_retrieve", `outcome`
    es. "error" / "empty" / "not_configured" / "mirror_failed"."""
    key = f"{component}:{outcome}"
    with _lock:
        _counts[key] += 1
        total = _counts[key]
    logger.warning(
        "degradation %s (count=%d)%s",
        key,
        total,
        f" — {detail}" if detail else "",
    )


def snapshot() -> dict[str, int]:
    with _lock:
        return dict(_counts)


def reset() -> None:
    with _lock:
        _counts.clear()
