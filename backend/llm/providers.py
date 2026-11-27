"""Quale fornitore serve un modello.

Il gateway sceglie il modello dal profilo del compito; da qui sceglie il client.
La regola e' il nome: i modelli di Anthropic si chiamano tutti `claude-...`,
tutto il resto passa dal client OpenAI (compresi gli endpoint compatibili dei
test, su `openai_base_url`).
"""

from __future__ import annotations

from enum import StrEnum


class Provider(StrEnum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


def provider_of(model: str) -> Provider:
    return Provider.ANTHROPIC if (model or "").strip().lower().startswith("claude-") else Provider.OPENAI
