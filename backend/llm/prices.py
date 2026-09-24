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

    LLM_PRICES_JSON={"gpt-5.6-luna": {"input": 1.25, "output": 10.0, "cached_input": 0.125}}
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
        if token_in is None or token_out is None:
            logger.error("LLM_PRICES_JSON: %s deve avere `input` e `output` numerici", model)
            continue
        prices[str(model).strip().lower()] = ModelPrice(
            input=token_in,
            output=token_out,
            cached_input=_decimal(entry.get("cached_input")),
        )
    return prices


def price_for(model: str) -> ModelPrice | None:
    """Il prezzo di un modello, o `None` se non e' configurato."""
    return _load().get((model or "").strip().lower())


def estimate_cost(
    model: str,
    *,
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int = 0,
) -> Decimal | None:
    """Il costo stimato di una chiamata, o `None` se il modello non ha prezzo.

    I token di ragionamento non sono un parametro a parte: il fornitore li
    fattura come uscita, quindi chi chiama li ha gia' dentro `output_tokens`.
    Contarli due volte gonfierebbe ogni stima.

    Args:
        model: Il nome del modello, come lo riporta il fornitore.
        input_tokens: Token letti, **compresi** quelli serviti dalla cache.
        output_tokens: Token prodotti, ragionamento compreso.
        cached_input_tokens: Quanti degli `input_tokens` venivano dalla cache.

    Returns:
        Il costo, o `None` quando il prezzo non si sa - che e' un'informazione,
        non un guasto.
    """
    price = price_for(model)
    if price is None:
        return None

    cached = max(0, min(cached_input_tokens, max(0, input_tokens)))
    full_price_input = max(0, input_tokens) - cached
    cached_rate = price.cached_input if price.cached_input is not None else price.input

    total = (
        Decimal(full_price_input) * price.input
        + Decimal(cached) * cached_rate
        + Decimal(max(0, output_tokens)) * price.output
    )
    return total / _PER_MILLION
