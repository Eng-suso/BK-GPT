"""Da token a euro, quando il prezzo si sa. E quando non si sa, lo dice.

La tentazione, scrivendo questo modulo, e' incollare il listino di oggi nel
codice. Sarebbe la seconda volta che ci sbagliamo sui numeri: il piano diceva
retry=1 perche' leggeva il default, mentre `.env` diceva 2. Un listino incollato
qui invecchia in silenzio e produce un costo *plausibile e falso*, che e' peggio
di nessun costo - perche' ci si fanno i budget sopra.

Quindi: i token si registrano **sempre**, il costo solo se il modello ha un
prezzo configurato. Un costo mancante e' `NULL` nel registro e si vede nelle
query; L10 (riconciliazione con la fattura) e' il controllo che dice se i prezzi
configurati sono quelli veri.

Configurazione: `LLM_PRICES_JSON` in `.env`, dollari (o euro: l'unita' e' quella
che ci metti, il codice non converte) per **milione** di token.

    LLM_PRICES_JSON={"gpt-6-luna": {"input": 0.10, "output": 0.50, "cached_input": 0.01}}

Per i modelli Claude va anche `cache_write`: Anthropic fattura la scrittura in
cache (1,25 volte l'ingresso con la durata di 5 minuti), OpenAI no.

    LLM_PRICES_JSON={"claude-haiku-5-5": {"input": 0.10, "output": 0.50, "cached_input": 0.01, "cache_write": 0.125}}
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from decimal import Decimal, InvalidOperation

from backend.settings import settings

logger = logging.getLogger(__name__)

_PER_MILLION = Decimal(1_000_000)


@dataclass(frozen=True, slots=True)
class ModelPrice:
    """Prezzo per milione di token.

    Attributes:
        input: Token letti, a prezzo pieno.
        output: Token prodotti. Include i token di ragionamento, che il
            fornitore fattura come uscita anche quando non li mostra.
        cached_input: Token letti serviti dalla cache del fornitore. `None` se
            non e' configurato: in quel caso i token in cache si contano al
            prezzo di input, che sovrastima e non sottostima.
    """

    input: Decimal
    output: Decimal
    cached_input: Decimal | None = None
    # I token scritti in cache, per i fornitori che li fanno pagare a parte
    # (Anthropic). `None`: si contano al prezzo di input, che e' il caso OpenAI.
    cache_write: Decimal | None = None
    # Per i modelli che si pagano a minuto di audio (la trascrizione dal vivo):
    # il prezzo di un minuto. Si somma al costo dei token, se ce ne sono.
    per_minute: Decimal | None = None


def _decimal(value: object) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _load() -> dict[str, ModelPrice]:
    """Il listino, riletto solo quando la configurazione cambia.

    La cache e' chiavata sul testo grezzo e non su niente: `price_for` gira a
    ogni riga del registro, cioe' a ogni chiamata al modello, e senza cache
    questo modulo riparserebbe il JSON ogni volta e ripeterebbe gli stessi
    errori nel log a ogni chiamata. Un test che cambia `llm_prices_json` vede
    comunque il valore nuovo, perche' cambia la chiave.
    """
    return _parse((settings.llm_prices_json or "").strip())


@lru_cache(maxsize=4)
def _parse(raw: str) -> dict[str, ModelPrice]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # Un listino illeggibile non deve fermare il prodotto: si perde il costo
        # stimato, non la chiamata. Ma va detto forte, perche' da qui in avanti
        # ogni riga del registro avra' `cost` a NULL.
        logger.error("LLM_PRICES_JSON non e' JSON valido: i costi stimati restano NULL")
        return {}
    if not isinstance(parsed, dict):
        logger.error("LLM_PRICES_JSON deve essere un oggetto {modello: prezzi}")
        return {}

    prices: dict[str, ModelPrice] = {}
    for model, entry in parsed.items():
        if not isinstance(entry, dict):
            logger.error("LLM_PRICES_JSON: il prezzo di %s non e' un oggetto", model)
            continue
        token_in = _decimal(entry.get("input"))
        token_out = _decimal(entry.get("output"))
        per_minute = _decimal(entry.get("per_minute"))
        # Un modello a minuto puo' non avere prezzi a token: valgono zero.
        if per_minute is not None:
            token_in = token_in if token_in is not None else Decimal(0)
            token_out = token_out if token_out is not None else Decimal(0)
        if token_in is None or token_out is None:
            logger.error("LLM_PRICES_JSON: %s deve avere `input` e `output` numerici (o `per_minute`)", model)
            continue
        prices[str(model).strip().lower()] = ModelPrice(
            input=token_in,
            output=token_out,
            cached_input=_decimal(entry.get("cached_input")),
            cache_write=_decimal(entry.get("cache_write")),
            per_minute=per_minute,
        )
    return prices


def price_for(model: str) -> ModelPrice | None:
    """Il prezzo di un modello, o `None` se non e' configurato."""
    return _load().get((model or "").strip().lower())


def configured_models() -> set[str]:
    """Ogni modello che questa configurazione puo' chiamare, e quindi fatturare.

    Il modello di ogni compito (chat, gateway, embedding, trascrizione dei file),
    la trascrizione dal vivo e l'estrattore di Mem0, quando Mem0 e' acceso.
    """
    from backend.llm.tasks import LlmTask, profile_for
    from backend.settings import settings

    models = {profile_for(task).model for task in LlmTask}
    models.add(settings.openai_live_transcription_model)
    if settings.mem0_database_url:
        models.add(settings.mem0_llm_model)
    return {m.strip().lower() for m in models if m and m.strip()}


def unpriced_models() -> list[str]:
    """I modelli configurati che il listino non conosce.

    Una loro riga nel registro si conterebbe al prezzo di ripiego, pessimista di
    proposito (`usage_unpriced_usd_per_million_tokens`): con i limiti di spesa
    accesi una persona verrebbe fermata dopo pochi turni per una spesa che non
    ha fatto.
    """
    return sorted(m for m in configured_models() if price_for(m) is None)


def estimate_cost(
    model: str,
    *,
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int = 0,
    cache_write_input_tokens: int = 0,
    audio_seconds: int = 0,
) -> Decimal | None:
    """Il costo stimato di una chiamata, o `None` se il modello non ha prezzo.

    I token di ragionamento non sono un parametro a parte: il fornitore li
    fattura come uscita, quindi chi chiama li ha gia' dentro `output_tokens`.
    Contarli due volte gonfierebbe ogni stima.

    Args:
        model: Il nome del modello, come lo riporta il fornitore.
        input_tokens: Token letti, **compresi** quelli serviti dalla cache e
            quelli scritti in cache.
        output_tokens: Token prodotti, ragionamento compreso.
        cached_input_tokens: Quanti degli `input_tokens` venivano dalla cache.
        cache_write_input_tokens: Quanti degli `input_tokens` sono stati scritti
            in cache. Si pagano a `cache_write` quando il listino lo dice.
        audio_seconds: I secondi di audio, per i modelli con un prezzo al minuto.

    Returns:
        Il costo, o `None` quando il prezzo non si sa - che e' un'informazione,
        non un guasto.
    """
    price = price_for(model)
    if price is None:
        return None

    total_input = max(0, input_tokens)
    cached = max(0, min(cached_input_tokens, total_input))
    written = max(0, min(cache_write_input_tokens, total_input - cached))
    full_price_input = total_input - cached - written
    cached_rate = price.cached_input if price.cached_input is not None else price.input
    write_rate = price.cache_write if price.cache_write is not None else price.input

    total = (
        Decimal(full_price_input) * price.input
        + Decimal(cached) * cached_rate
        + Decimal(written) * write_rate
        + Decimal(max(0, output_tokens)) * price.output
    ) / _PER_MILLION
    if price.per_minute is not None:
        total += Decimal(max(0, audio_seconds)) / Decimal(60) * price.per_minute
    return total
