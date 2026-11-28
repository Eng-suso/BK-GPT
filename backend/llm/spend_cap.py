"""Il freno d'emergenza: un tetto di spesa per tutta l'installazione, sulle 24 ore.

Il contatore d'uso (`budget.py`) ferma il consulente alla richiesta successiva,
e lascia arrivare in fondo il lavoro gia' accettato: lettura dei file, grafo,
memoria, ricostruzione del piano. E' giusto per il consulente, ma lascia aperta
la porta da cui il credito e' finito il 18/09: un difetto che fa partire cento
chiamate in background non lo ferma nessun limite per persona.

Questo tetto non guarda chi spende: guarda quanto ha speso l'installazione nelle
ultime 24 ore, dal registro dei consumi, e quando lo supera:

- il gateway, il client della chat e Mem0 rifiutano le chiamate nuove, e la riga
  del registro lo dice (`refused`, `SpendCapReached`);
- le code smettono di prendere lavori: restano in coda, non si perdono, e
  ripartono da sole quando la finestra delle 24 ore scorre (`supervisor`);
- la chat, le azioni dirette e le registrazioni rispondono 429 con un messaggio
  per il consulente.

`SpendCapReached` e' una `MissingProviderKey`: ogni punto che oggi sa andare
avanti senza chiave (il rerank lessicale, la risoluzione delle entita' per
regole) fa lo stesso a tetto raggiunto, invece di rompersi.

Non sostituisce il limite di spesa sulla console del fornitore, che resta la
rete di sicurezza per cio' che il registro non vede. Lo rende raro.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from backend.llm_config import MissingProviderKey
from backend.settings import settings

_WINDOW = timedelta(hours=24)
#: Quanto vale una lettura del registro. Il tetto si controlla a ogni chiamata
#: al modello: senza cache sarebbe una query per chiamata.
_CACHE_SECONDS = 30.0
_MILLION = Decimal(1_000_000)

MESSAGE = (
    "Il servizio ha raggiunto il tetto di spesa giornaliero dell'installazione. "
    "Riprende da solo entro 24 ore; l'amministratore puo' alzarlo."
)

_cache: tuple[float, Decimal] | None = None
logger = logging.getLogger(__name__)


class SpendCapReached(MissingProviderKey):
    """Il tetto di spesa dell'installazione e' raggiunto: la chiamata non parte."""


def _limit() -> Decimal | None:
    value = Decimal(str(settings.usage_hard_cap_daily_usd or 0))
    return value if value > 0 else None


def spent_last_24h(now: datetime | None = None) -> Decimal:
    """La spesa delle ultime 24 ore, modelli e audio, di tutti i tenant.

    Le righe dei modelli senza prezzo si contano al prezzo di ripiego,
    pessimista, come nel contatore d'uso: un costo sconosciuto fa scattare il
    freno prima, mai dopo. L'audio senza prezzo al minuto non ha un ripiego
    sensato a token e resta fuori: il suo tetto e' in ore, nel contatore.
    """
    from backend.llm import ledger

    end = now or datetime.now(UTC)
    start = (end - _WINDOW).isoformat()
    models, audio = ledger.per_finestre({"day": start}, fine=end.isoformat())
    rate = Decimal(str(settings.usage_unpriced_usd_per_million_tokens))
    day_models, day_audio = models["day"], audio["day"]
    return day_models.costo_noto + day_audio.costo_noto + Decimal(day_models.token_senza_prezzo) * rate / _MILLION


def tripped() -> bool:
    """Se il tetto e' raggiunto. Spento (`USAGE_HARD_CAP_DAILY_USD=0`): mai."""
    global _cache
    limit = _limit()
    if limit is None:
        return False
    now = time.monotonic()
    if _cache is None or now - _cache[0] > _CACHE_SECONDS:
        try:
            _cache = (now, spent_last_24h())
        except Exception:  # noqa: BLE001 - il freno non deve fermare le code se il registro non risponde
            # Si tiene l'ultima lettura (o nessun freno, se non ce n'e' una) e si
            # riprova alla prossima scadenza della cache, invece di sollevare
            # dentro i loop dei worker o a ogni chiamata.
            logger.warning("tetto di spesa: lettura del registro fallita", exc_info=True)
            _cache = (now, _cache[1] if _cache is not None else Decimal(0))
    return _cache[1] >= limit


def check() -> None:
    """Il permesso di spendere, chiesto da ogni punto che sta per chiamare un modello.

    Raises:
        SpendCapReached: Se il tetto delle 24 ore e' raggiunto.
    """
    if tripped():
        raise SpendCapReached(MESSAGE)


def reset_cache() -> None:
    """Dimentica l'ultima lettura. Per i test: il tetto si rilegge dai settings a
    ogni chiamata, quindi alzarlo vale subito anche senza questa funzione."""
    global _cache
    _cache = None


def pause_while_tripped(name: str, *, poll_seconds: float = 30.0) -> None:
    """Per i worker in processi a se' (`python -m backend.workers.*`): aspetta.

    Stessa regola del supervisore in-process: a tetto raggiunto non si prendono
    lavori, e quelli in coda aspettano invece di fallire.
    """
    import logging

    logger = logging.getLogger(__name__)
    if not tripped():
        return
    logger.warning("%s: in pausa, tetto di spesa dell'installazione raggiunto", name)
    while tripped():
        time.sleep(poll_seconds)
    logger.info("%s: riprende, la spesa e' tornata sotto il tetto", name)
