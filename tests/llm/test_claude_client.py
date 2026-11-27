"""Claude nel gateway: la cache si conta e si paga come la fattura.

Anthropic, a differenza di OpenAI, fa pagare la scrittura in cache (1,25 volte
l'ingresso con la durata di 5 minuti). Un registro che contasse quei token al
prezzo d'ingresso direbbe meno di quanto si spende davvero.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.llm.prices import estimate_cost
from backend.llm.usage import tokens_from_usage_metadata
from backend.settings import settings

HAIKU_PRICES = (
    '{"claude-haiku-5-5": {"input": 0.10, "output": 0.50, "cached_input": 0.01, "cache_write": 0.125}}'
)


@pytest.fixture
def haiku_prices(monkeypatch):
    monkeypatch.setattr(settings, "llm_prices_json", HAIKU_PRICES)


class TestScritturaInCache:
    def test_le_scritture_si_pagano_a_parte(self, haiku_prices):
        # 1M in ingresso: 600K letti dalla cache, 300K scritti, 100K nuovi.
        cost = estimate_cost(
            "claude-haiku-5-5",
            input_tokens=1_000_000,
            output_tokens=0,
            cached_input_tokens=600_000,
            cache_write_input_tokens=300_000,
        )
        assert cost == Decimal("0.6") * Decimal("0.01") + Decimal("0.3") * Decimal("0.125") + Decimal("0.1") * Decimal("0.10")

    def test_senza_prezzo_della_scrittura_vale_l_ingresso(self, monkeypatch):
        monkeypatch.setattr(settings, "llm_prices_json", '{"gpt-6-luna": {"input": 0.10, "output": 0.50}}')
        cost = estimate_cost("gpt-6-luna", input_tokens=1_000_000, output_tokens=0, cache_write_input_tokens=400_000)
        assert cost == Decimal("0.10")

    def test_le_scritture_non_superano_l_ingresso(self, haiku_prices):
        cost = estimate_cost(
            "claude-haiku-5-5", input_tokens=100, output_tokens=0, cached_input_tokens=80, cache_write_input_tokens=500
        )
        assert cost == (Decimal(80) * Decimal("0.01") + Decimal(20) * Decimal("0.125")) / Decimal(1_000_000)


class TestTokenDiClaude:
    def test_scritture_in_cache_creation(self):
        tokens = tokens_from_usage_metadata({
            "input_tokens": 1_000, "output_tokens": 50,
            "input_token_details": {"cache_read": 600, "cache_creation": 300},
        })
        assert (tokens.input, tokens.cached_input, tokens.cache_write_input) == (1_000, 600, 300)

    def test_scritture_divise_per_durata_si_contano_una_volta(self):
        # Con le voci per TTL langchain-anthropic azzera `cache_creation`.
        tokens = tokens_from_usage_metadata({
            "input_tokens": 1_000, "output_tokens": 50,
            "input_token_details": {"cache_read": 0, "cache_creation": 0, "ephemeral_5m_input_tokens": 400},
        })
        assert tokens.cache_write_input == 400

    def test_openai_non_ha_scritture(self):
        tokens = tokens_from_usage_metadata({
            "input_tokens": 1_000, "output_tokens": 50, "input_token_details": {"cache_read": 500},
        })
        assert tokens.cache_write_input == 0
