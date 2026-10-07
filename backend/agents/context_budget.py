"""Quanto contesto entra nel prompt, deciso dal runtime e dichiarato al modello.

Il prompt di scope mette insieme regole brevi e artefatti lunghi: il piano,
il modello semantico, il quality report, l'XML del canvas. Ognuno aveva il
suo tetto in caratteri (40.000, 80.000 per l'XML) e nessuno il tetto del
totale: otto artefatti e due XML al massimo fanno 480.000 caratteri in un
solo messaggio di sistema, e cosa restava fuori lo decideva il punto in cui
il carattere numero 40.000 cadeva, dentro ciascun artefatto.

Qui il totale ha un budget in token. Gli artefatti sono blocchi con una
priorita': entrano interi finche' c'e' spazio, poi uno si tronca, gli altri
restano fuori. Mai in silenzio: al posto di quello che manca il modello legge
cosa manca e quanto pesava, cosi' puo' chiederlo o rileggerlo con un tool
invece di ragionare su un piano a meta' credendolo intero.

Il risultato porta l'impronta (sha256) del testo finale e il conto di cosa e'
entrato: due turni con la stessa impronta hanno visto lo stesso contesto.
Chi assembla il contesto di un turno la annota (`note_context_fingerprint`),
e il runtime la raccoglie per la riga del registro dei consumi.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import lru_cache
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    import tiktoken

logger = logging.getLogger(__name__)

# Sotto questa soglia un blocco troncato non dice piu' niente di utile: meglio
# ometterlo e dirlo, che consegnarne l'intestazione.
MIN_TRUNCATED_TOKENS = 400

Fate = Literal["included", "truncated", "omitted"]


class ContextBudgetExceeded(RuntimeError):
    """Le sole righe fisse (regole, id, contratti) superano il budget.

    Non si tagliano: sono il contratto del turno. Succede solo con un budget
    configurato piu' piccolo delle regole stesse, ed e' un errore di
    configurazione da vedere, non un prompt da mandare fuori misura.
    """


@lru_cache(maxsize=1)
def _encoding() -> tiktoken.Encoding | None:
    try:
        import tiktoken

        return tiktoken.get_encoding("o200k_base")
    except (ImportError, OSError, ValueError):
        # Pacchetto assente, o file della codifica non scaricabile (la rete
        # passa da OSError): si stima per eccesso, e si dice.
        logger.warning("tokenizer o200k_base non disponibile: stima per eccesso in byte", exc_info=True)
        return None


def count_tokens(text: str) -> int:
    """Token del testo per la famiglia di modelli in uso (o200k).

    Senza tokenizer (pacchetto o file di codifica mancanti) conta i byte UTF-8:
    un token o200k e' almeno un byte, quindi il conto non sta mai sotto quello
    vero. Il budget deve sbagliare dalla parte sicura, anche di molto.
    """
    if not text:
        return 0
    encoding = _encoding()
    if encoding is None:
        return len(text.encode("utf-8"))
    return len(encoding.encode(text, disallowed_special=()))


def _truncate_to_tokens(text: str, max_tokens: int) -> str:
    encoding = _encoding()
    if encoding is None:
        return text.encode("utf-8")[:max_tokens].decode("utf-8", errors="ignore")
    return encoding.decode(encoding.encode(text, disallowed_special=())[:max_tokens])


@dataclass(frozen=True)
class ContextBlock:
    """Un artefatto del prompt che si puo' troncare o lasciare fuori.

    `priority` piu' alta entra prima. `header` sono le righe che lo introducono
    e restano anche quando il corpo e' troncato.
    """

    name: str
    body: str
    priority: int
    header: tuple[str, ...] = ()


@dataclass(frozen=True)
class BlockOutcome:
    name: str
    fate: Fate
    tokens: int
    full_tokens: int


@dataclass(frozen=True)
class ContextReport:
    budget_tokens: int
    total_tokens: int
    fingerprint: str
    blocks: tuple[BlockOutcome, ...] = field(default_factory=tuple)

    def as_log(self) -> dict[str, object]:
        return {
            "budget_tokens": self.budget_tokens,
            "total_tokens": self.total_tokens,
            "fingerprint": self.fingerprint,
            "blocks": {b.name: f"{b.fate}:{b.tokens}/{b.full_tokens}" for b in self.blocks},
        }


@dataclass(frozen=True)
class AssembledContext:
    text: str
    report: ContextReport


def assemble(parts: Sequence[str | ContextBlock], budget_tokens: int) -> AssembledContext:
    """Ricompone il prompt nell'ordine scritto, con i blocchi dentro il budget.

    Le righe semplici (regole, id, contratti) entrano sempre: sono poche e
    sono il contratto del turno. Il budget che resta si distribuisce ai
    blocchi per priorita'. A parita' di priorita' vince chi viene prima.
    """
    blocks = [part for part in parts if isinstance(part, ContextBlock)]
    order = sorted(range(len(blocks)), key=lambda i: (-blocks[i].priority, i))
    body_tokens = [count_tokens(block.body) for block in blocks]
    full_tokens = [
        count_tokens("\n".join(block.header)) + n
        for block, n in zip(blocks, body_tokens, strict=True)
    ]

    # Primo giro, a stima: le righe fisse prima, poi i blocchi per priorita'.
    # `allowance[i]` = token di corpo concessi: tutti, una parte, o zero.
    fixed = "\n".join(part for part in parts if isinstance(part, str))
    fixed_tokens = count_tokens(fixed)
    if fixed_tokens > budget_tokens:
        raise ContextBudgetExceeded(
            f"le righe fisse del contesto sono {fixed_tokens} token, il budget {budget_tokens}"
        )
    remaining = budget_tokens - fixed_tokens
    allowance: dict[int, int] = {}
    for i in order:
        if full_tokens[i] <= remaining:
            allowance[i] = body_tokens[i]
            remaining -= full_tokens[i]
            continue
        room = remaining - (full_tokens[i] - body_tokens[i]) - _NOTE_TOKENS
        allowance[i] = room if room >= MIN_TRUNCATED_TOKENS else 0
        remaining = max(0, remaining - allowance[i] - _NOTE_TOKENS)

    # Poi si misura il testo vero (separatori e note compresi) e, se sfora,
    # si stringe il blocco meno importante ancora presente finche' rientra.
    text, outcomes = _render(parts, blocks, allowance, body_tokens, full_tokens)
    total = count_tokens(text)
    for i in reversed(order):
        while total > budget_tokens and allowance[i] > 0:
            shrunk = min(allowance[i], body_tokens[i]) - (total - budget_tokens) - _NOTE_TOKENS
            allowance[i] = shrunk if shrunk >= MIN_TRUNCATED_TOKENS else 0
            text, outcomes = _render(parts, blocks, allowance, body_tokens, full_tokens)
            total = count_tokens(text)

    report = ContextReport(
        budget_tokens=budget_tokens,
        total_tokens=total,
        fingerprint=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        blocks=tuple(outcomes),
    )
    return AssembledContext(text=text, report=report)


# Le impronte dei contesti assemblati nel turno in corso. La lista e' una sola
# per turno e si condivide per riferimento: i nodi di LangGraph girano in thread
# che ricevono una copia del contesto, e un append li' si vede dal runtime.
_turn_fingerprints: ContextVar[list[str] | None] = ContextVar(
    "delir_context_fingerprints", default=None
)


@contextmanager
def collect_context_fingerprints() -> Iterator[list[str]]:
    """Raccoglie le impronte dei contesti assemblati dentro il blocco.

    La apre il runtime intorno al turno; fuori da un turno annotare non fa
    niente. Yields la lista, in ordine di assemblaggio.
    """
    seen: list[str] = []
    token = _turn_fingerprints.set(seen)
    try:
        yield seen
    finally:
        _turn_fingerprints.reset(token)


def note_context_fingerprint(fingerprint: str) -> None:
    """Annota l'impronta di un contesto mandato al modello nel turno in corso."""
    seen = _turn_fingerprints.get()
    if seen is not None:
        seen.append(fingerprint)


# Quanto costa la riga che dichiara un taglio o un'omissione, per eccesso.
_NOTE_TOKENS = 60


def _render(
    parts: Sequence[str | ContextBlock],
    blocks: list[ContextBlock],
    allowance: dict[int, int],
    body_tokens: list[int],
    full_tokens: list[int],
) -> tuple[str, list[BlockOutcome]]:
    rendered: list[list[str]] = []
    outcomes: list[BlockOutcome] = []
    for i, block in enumerate(blocks):
        allowed = allowance[i]
        if allowed >= body_tokens[i]:
            rendered.append([*block.header, block.body])
            outcomes.append(BlockOutcome(block.name, "included", full_tokens[i], full_tokens[i]))
        elif allowed > 0:
            note = (
                f"[{block.name} troncato dal budget del contesto: {allowed} token di "
                f"{full_tokens[i]}. Il resto non e' qui: se ti serve, rileggilo con un tool.]"
            )
            rendered.append([*block.header, _truncate_to_tokens(block.body, allowed), note])
            outcomes.append(
                BlockOutcome(
                    block.name,
                    "truncated",
                    full_tokens[i] - body_tokens[i] + allowed,
                    full_tokens[i],
                )
            )
        else:
            note = (
                f"[{block.name} omesso dal budget del contesto ({full_tokens[i]} token). "
                "Non e' assente: non e' stato inviato. Se ti serve, rileggilo con un tool.]"
            )
            rendered.append(["", note])
            outcomes.append(BlockOutcome(block.name, "omitted", 0, full_tokens[i]))

    lines: list[str] = []
    rendered_blocks = iter(rendered)
    for part in parts:
        if isinstance(part, str):
            lines.append(part)
        else:
            lines.extend(next(rendered_blocks))
    return "\n".join(lines), outcomes
