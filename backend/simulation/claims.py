"""Le affermazioni dei file del cliente proposte come fonte di un parametro (SIM-07, C3).

Gate G5, deciso l'8 ottobre: l'abbinamento affermazione -> attivita' e' lessicale
sul nome e sempre **proposto**; diventa fonte ``declared`` del parametro solo
quando il consulente lo conferma. Una durata citata ("circa 2 giorni") resta un
riferimento accanto al valore, non lo sostituisce.

Il confronto ignora maiuscole, accenti e parole vuote, e confronta le parole per
radice (le prime cinque lettere): "approvazione" e "approva" si riconoscono.
Pure funzioni: nessun accesso al database.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_STEM = 5
_MIN_WORD = 4
_MAX_PROPOSALS = 3
_STOPWORDS = {
    "della", "delle", "dello", "degli", "alla", "alle", "allo", "agli", "dalla", "dalle", "dallo", "dagli",
    "nella", "nelle", "nello", "negli", "sulla", "sulle", "sullo", "sugli", "questo", "questa", "quello",
    "quella", "sono", "viene", "vengono", "essere", "fare", "come", "anche", "dopo", "prima", "ogni",
    "with", "from", "that", "this", "into", "then", "each",
}
_NUMBERS = {"un": 1, "uno": 1, "una": 1, "due": 2, "tre": 3, "quattro": 4, "cinque": 5, "sei": 6, "sette": 7,
            "otto": 8, "nove": 9, "dieci": 10, "quindici": 15, "venti": 20, "trenta": 30}
_UNITS = (
    (r"minut[oi]|min\b", 60),
    (r"or[ae]\b|h\b", 3600),
    (r"giorn[oi]|gg\b", 86_400),
    (r"settiman[ae]", 604_800),
)
_DURATION = re.compile(
    r"(?P<amount>\d+(?:[.,]\d+)?|" + "|".join(_NUMBERS) + r")\s*(?:'\s*)?(?P<unit>"
    + "|".join(pattern for pattern, _ in _UNITS) + r")",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class SourceClaim:
    """Un'affermazione di un file, come la legge l'abbinamento."""

    id: int
    statement: str
    quote: str
    quote_verified: bool
    source_id: str


@dataclass(frozen=True, slots=True)
class DurationHint:
    """Una durata citata nella fonte: il testo com'e' e il suo valore in secondi."""

    text: str
    seconds: float


@dataclass(frozen=True, slots=True)
class ClaimProposal:
    claim_id: int
    statement: str
    quote: str
    quote_verified: bool
    source_id: str
    source_name: str
    score: float
    duration_hint: DurationHint | None


def _words(text: str) -> set[str]:
    plain = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode("ascii")
    return {w[:_STEM] for w in re.findall(r"[a-z]+", plain) if len(w) >= _MIN_WORD and w not in _STOPWORDS}


def duration_hint(text: str) -> DurationHint | None:
    """La prima durata citata nel testo ("circa 2 giorni", "mezz'ora"), se c'e'."""
    if re.search(r"\bmezz'?\s*ora\b", text, re.IGNORECASE):
        return DurationHint(text="mezz'ora", seconds=1800.0)
    match = _DURATION.search(text)
    if match is None:
        return None
    raw = match.group("amount").lower()
    amount = float(_NUMBERS[raw]) if raw in _NUMBERS else float(raw.replace(",", "."))
    unit = match.group("unit").lower()
    factor = next(f for pattern, f in _UNITS if re.fullmatch(pattern, unit, re.IGNORECASE))
    return DurationHint(text=match.group(0), seconds=amount * factor)


def propose(activity_name: str, claims: list[SourceClaim], sources: dict[str, str]) -> list[ClaimProposal]:
    """Le affermazioni che nominano l'attivita', le piu' vicine per prime (al massimo tre).

    ``sources`` va da id a nome del file.
    """
    wanted = _words(activity_name)
    if not wanted:
        return []
    proposals = []
    for claim in claims:
        found = wanted & _words(f"{claim.statement} {claim.quote}")
        score = len(found) / len(wanted)
        # Un nome di una parola sola deve esserci; uno lungo almeno per meta'.
        if not found or score < 0.5:
            continue
        proposals.append(ClaimProposal(
            claim_id=claim.id,
            statement=claim.statement,
            quote=claim.quote,
            quote_verified=claim.quote_verified,
            source_id=claim.source_id,
            source_name=sources.get(claim.source_id, claim.source_id),
            score=round(score, 2),
            duration_hint=duration_hint(f"{claim.quote} {claim.statement}"),
        ))
    proposals.sort(key=lambda p: (-p.score, not p.quote_verified, p.claim_id))
    return proposals[:_MAX_PROPOSALS]
