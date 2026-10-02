"""Come si confronta cio' che una persona scrive in un campo di ricerca.

Le due ricerche del prodotto - quella nella cronologia delle conversazioni e
quella globale sul workspace - devono comportarsi allo stesso modo: le stesse
parole trovano le stesse cose, e un `%` scritto per caso cerca un `%` invece di
restituire tutto. La regola sta qui una volta sola, invece di essere riscritta
in ogni modulo che interroga.
"""

from __future__ import annotations

# Quanto testo mostrare intorno alla parola trovata, da un lato e dall'altro.
SEARCH_SNIPPET_RADIUS = 90
# Le parole oltre la quinta non restringono piu' niente di utile e allungano solo
# la query: una ricerca e' un modo per ritrovare qualcosa, non una
# interrogazione full-text.
SEARCH_MAX_TERMS = 5


def like_escape(value: str) -> str:
    """Rende letterali i caratteri che LIKE interpreta.

    Senza, chi cerca `100%` chiede "qualunque cosa dopo 100" e chi cerca
    `client_id` trova anche `clientXid`.
    """
    for char in ("\\", "%", "_"):
        value = value.replace(char, f"\\{char}")
    return value


def search_terms(query: str) -> list[str]:
    """Le parole della ricerca, normalizzate, al piu' `SEARCH_MAX_TERMS`."""
    return [term.lower() for term in query.split()][:SEARCH_MAX_TERMS]


def like_patterns(terms: list[str]) -> list[str]:
    """Un pattern `%parola%` per parola, coi caratteri speciali gia' resi letterali."""
    return [f"%{like_escape(term)}%" for term in terms]


def snippet(content: str, terms: list[str]) -> str:
    """Il pezzo di testo intorno alla prima parola trovata.

    Un risultato senza contesto non si distingue dagli altri: il titolo di una
    chat e' quasi sempre la prima domanda, e dieci conversazioni sullo stesso
    processo hanno titoli quasi identici. Cio' che dice quale riaprire e' la
    riga in cui la parola compare.
    """
    compact = " ".join(content.split())
    lowered = compact.lower()
    position = min(
        (found for found in (lowered.find(term) for term in terms) if found >= 0),
        default=-1,
    )
    if position < 0:
        return compact[: SEARCH_SNIPPET_RADIUS * 2].rstrip()

    start = max(0, position - SEARCH_SNIPPET_RADIUS)
    end = min(len(compact), position + SEARCH_SNIPPET_RADIUS)
    return (
        ("..." if start > 0 else "")
        + compact[start:end].strip()
        + ("..." if end < len(compact) else "")
    )


def match_rank(text: str, terms: list[str]) -> int:
    """Quanto un testo corrisponde: 0 esatto, 1 comincia cosi', 2 lo contiene.

    Chi scrive "acqu" cerca "Acquisti", non un processo che nomina gli acquisti
    a meta' frase: senza un ordine, il risultato giusto finisce sotto i
    parenti lunghi.
    """
    lowered = " ".join(text.split()).lower()
    joined = " ".join(terms)
    if lowered == joined:
        return 0
    if lowered.startswith(joined) or any(
        word.startswith(terms[0]) for word in lowered.split()
    ):
        return 1
    return 2
