"""Quando riprovare, quanto aspettare, e quando smettere.

I worker delle code trattavano ogni errore allo stesso modo: `attempts + 1` e
via al giro dopo. Con `idle_sleep` di due secondi e un batch da 200 righe questo
significa che un rate limit del provider brucia i cinque tentativi in una
manciata di secondi, e la riga finisce in dead-letter per un guasto che sarebbe
passato da solo. Nella direzione opposta, un payload che non potra' mai essere
applicato veniva riprovato cinque volte prima di fermarsi.

Sono tre esiti diversi, e qui restano distinti:

    permanent  il job non puo' riuscire, ne' ora ne' mai (payload malformato,
               operazione sconosciuta) -> dead-letter subito, senza ritentare
    throttled  il provider ha detto "non ora" (429 / TPM). L'attesa la decide
               lui quando la dichiara (`Retry-After`, "try again in 1.2s"),
               e **non consuma** il budget dei tentativi: un limite di banda
               non e' un difetto del job
    exhausted  il provider ha detto "non piu'": credito o quota finiti. Arriva
               anche lui come 429, ma aspettare non lo risolve - serve una
               persona che ricarichi l'account. Non consuma tentativi ne'
               budget di banda (non e' colpa del job, e bruciarli manderebbe
               in dead-letter l'intera coda mentre nessuno puo' fare niente),
               e ferma l'intera coda per una pausa lunga invece di sondare il
               provider riga per riga
    transient  tutto il resto (rete, indisponibilita' momentanea) -> attesa
               esponenziale con jitter, e il tentativo si consuma
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Literal

# Attesa esponenziale: 2, 4, 8, 16, 32 ... con full jitter, tetto a 15 minuti.
BASE_DELAY_SECONDS = 2.0
MAX_DELAY_SECONDS = 900.0

# Un `Retry-After` piu' lungo di questo non viene onorato alla lettera: un
# header sbagliato (o ostile) non deve poter parcheggiare una riga per un giorno.
MAX_HONORED_RETRY_AFTER_SECONDS = 300.0

# Dopo tanti rifiuti per banda, il rifiuto smette di essere gratis. Una coda che
# prende 429 all'infinito non sta aspettando il proprio turno: ha una quota
# esaurita o una chiave sbagliata, e deve poter finire in dead-letter come
# qualunque altro guasto, invece di ritentare in eterno senza che nessuno guardi.
THROTTLE_BUDGET = 12

# Credito o quota finiti: si riprova di rado, perche' riprovare non cambia niente
# finche' qualcuno non ricarica l'account.
EXHAUSTED_PAUSE_SECONDS = 900.0

FailureKind = Literal["permanent", "throttled", "exhausted", "transient"]

_RATE_LIMIT_NAMES = ("ratelimit", "toomanyrequests")
_RATE_LIMIT_TEXT = (
    "rate limit",
    "rate_limit",
    "too many requests",
    "429",
    "tokens per min",
    "requests per min",
    "tpm",
    "rpm",
    "quota exceeded",
)
# OpenAI: `insufficient_quota` / `credit_balance_exhausted`, sempre con status 429.
_EXHAUSTED_TEXT = (
    "insufficient_quota",
    "credit_balance_exhausted",
    "exceeded your current quota",
    "no credits remaining",
)
# "Please try again in 1.2s" / "... in 320ms" / "... in 1m30s" (OpenAI)
_TRY_AGAIN = re.compile(r"try again in\s+([0-9]+(?:\.[0-9]+)?)\s*(ms|s|m)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Failure:
    """Come trattare un job fallito."""

    kind: FailureKind
    delay_seconds: float
    #: se False, il job non consuma un tentativo (il fallimento non e' suo)
    consumes_attempt: bool

    @property
    def is_permanent(self) -> bool:
        return self.kind == "permanent"


def backoff_delay(attempts: int, *, base: float = BASE_DELAY_SECONDS,
                  cap: float = MAX_DELAY_SECONDS) -> float:
    """Attesa esponenziale con full jitter dopo `attempts` fallimenti.

    Full jitter (`random.uniform(0, exp)`) e non l'esponenziale secco: quando la
    coda si ferma tutta insieme — ed e' cosi' che si ferma, per un guasto comune
    — l'esponenziale secco fa ripartire tutte le righe nello stesso istante e
    riproduce esattamente il picco che ha causato il guasto.

    Args:
        attempts: Quanti tentativi sono gia' stati consumati (>= 0).
        base: L'attesa del primo ritentativo.
        cap: Il tetto, prima del jitter.

    Returns:
        I secondi da aspettare, mai negativi.
    """
    exponential = min(cap, base * (2 ** max(0, int(attempts))))
    return random.uniform(base if exponential > base else 0.0, exponential)


def retry_after_seconds(exc: BaseException) -> float | None:
    """L'attesa dichiarata dal provider, se l'ha dichiarata.

    Legge prima l'header `Retry-After` della risposta (quando l'eccezione la
    porta con se', come quelle di `openai`/`httpx`), poi il testo del messaggio.

    Args:
        exc: L'eccezione sollevata dalla chiamata, non affidabile.

    Returns:
        I secondi da attendere, limitati a `MAX_HONORED_RETRY_AFTER_SECONDS`,
        oppure None se il provider non ha detto nulla di leggibile.
    """
    headers = getattr(getattr(exc, "response", None), "headers", None)
    if headers is not None:
        for name in ("retry-after", "retry-after-ms", "x-ratelimit-reset-tokens"):
            try:
                raw = headers.get(name)
            except Exception:  # noqa: BLE001 — header store esotico
                raw = None
            if raw is None:
                continue
            seconds = _parse_duration(str(raw), milliseconds=name.endswith("-ms"))
            if seconds is not None:
                return min(seconds, MAX_HONORED_RETRY_AFTER_SECONDS)

    match = _TRY_AGAIN.search(str(exc))
    if match:
        value = float(match.group(1))
        unit = match.group(2).lower()
        seconds = value / 1000.0 if unit == "ms" else value * 60.0 if unit == "m" else value
        return min(seconds, MAX_HONORED_RETRY_AFTER_SECONDS)
    return None


def is_rate_limit(exc: BaseException) -> bool:
    """Se l'errore e' un limite di banda del provider e non un difetto del job."""
    if getattr(exc, "status_code", None) == 429 or getattr(
        getattr(exc, "response", None), "status_code", None
    ) == 429:
        return True
    name = type(exc).__name__.lower()
    if any(hint in name for hint in _RATE_LIMIT_NAMES):
        return True
    message = str(exc).lower()
    return any(hint in message for hint in _RATE_LIMIT_TEXT)


def is_quota_exhausted(exc: BaseException) -> bool:
    """Se il provider rifiuta perche' credito o quota sono finiti, non per banda."""
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        nested = body.get("error")
        error = nested if isinstance(nested, dict) else body
        if {error.get("code"), error.get("type")} & {"insufficient_quota", "credit_balance_exhausted"}:
            return True
    message = str(exc).lower()
    return any(hint in message for hint in _EXHAUSTED_TEXT)


def classify(
    exc: BaseException,
    *,
    attempts: int,
    throttled: int = 0,
    permanent: tuple[type[BaseException], ...] = (),
) -> Failure:
    """Decide come trattare `exc` per un job gia' fallito `attempts` volte.

    Args:
        exc: L'eccezione della passata appena fallita, non affidabile.
        attempts: Tentativi gia' consumati da questo job.
        throttled: Quante volte questo job e' gia' stato respinto per banda.
            Non consuma tentativi, ma allunga l'attesa — e oltre
            `THROTTLE_BUDGET` il rifiuto torna a contare come guasto.
        permanent: Le eccezioni che questa coda considera definitive.

    Returns:
        Il verdetto: tipo, attesa e se il tentativo va contato.
    """
    if permanent and isinstance(exc, permanent):
        return Failure(kind="permanent", delay_seconds=0.0, consumes_attempt=True)
    if is_quota_exhausted(exc):
        return Failure(
            kind="exhausted",
            delay_seconds=EXHAUSTED_PAUSE_SECONDS * random.uniform(1.0, 1.1),
            consumes_attempt=False,
        )
    if is_rate_limit(exc):
        declared = retry_after_seconds(exc)
        # L'attesa cresce sul contatore dei throttle, non su quello dei
        # tentativi: e' il rifiuto ripetuto a dire quanto siamo sopra soglia.
        # Il jitter serve anche qui: se il provider dice "fra 20s" a tutta la
        # coda, tutta la coda non deve ripartire allo stesso ventesimo secondo.
        delay = (
            declared * random.uniform(1.0, 1.25)
            if declared is not None
            else backoff_delay(throttled)
        )
        return Failure(
            kind="throttled",
            delay_seconds=delay,
            consumes_attempt=throttled >= THROTTLE_BUDGET,
        )
    return Failure(
        kind="transient",
        delay_seconds=backoff_delay(attempts),
        consumes_attempt=True,
    )


def _parse_duration(raw: str, *, milliseconds: bool = False) -> float | None:
    """`Retry-After` numerico (secondi o millisecondi). Le date HTTP non si
    leggono qui: quando arrivano si ricade sul backoff, che e' sempre corretto."""
    try:
        value = float(raw.strip())
    except (TypeError, ValueError):
        return None
    if value < 0:
        return None
    return value / 1000.0 if milliseconds else value
