"""C3, seconda parte: il ripiego con un LLM economico per l'abbinamento (gate G5).

Il confronto lessicale di ``claims.py`` riconosce "approvazione" in "approva",
ma non "Verifica fattura" in "il controllo dei documenti contabili". Per le sole
attivita' rimaste senza proposte si chiede al modello quali affermazioni, fra
quelle mostrate, parlano di quell'attivita'. Le regole di G5 restano:

- l'abbinamento e' sempre **proposto**: diventa fonte ``declared`` solo quando
  il consulente lo conferma, come per il lessicale;
- il modello sceglie solo fra id che gli sono stati mostrati: un id inventato o
  di un'altra attivita' si scarta;
- un guasto del modello (rete, chiave, schema) non rompe il pannello: restano
  le proposte lessicali. Senza chiave il ripiego non parte.

Un pannello che si riapre non paga di nuovo: la risposta resta in una cache in
memoria per processo, attivita' e affermazioni.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import OrderedDict
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from backend.simulation.claims import ClaimProposal, SourceClaim, duration_hint

logger = logging.getLogger(__name__)

MAX_CLAIMS = 120
MAX_ACTIVITIES = 40
MAX_STATEMENT_CHARS = 240
MAX_PER_ACTIVITY = 3
_CACHE_SIZE = 64

SYSTEM = """Sei l'analista dei processi di DeliR. Ti do le attivita' di un processo,
ognuna con il suo id [A#], e le affermazioni dei documenti del cliente, ognuna con
il suo id [C#].

Per ogni attivita' indica le affermazioni che descrivono proprio quell'attivita'
(chi la fa, quanto dura, con quali regole), anche se usano parole diverse dal nome.

Regole:
- usa solo id che compaiono qui sotto;
- al massimo tre affermazioni per attivita', le piu' pertinenti per prime;
- se nessuna affermazione parla di un'attivita', lasciala senza affermazioni;
- un'affermazione generica sul processo intero non e' di nessuna attivita'."""


class _ActivityMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    activity: str = Field(description="L'id dell'attivita', es. A3")
    # Niente tetto nello schema: una risposta con un id in piu' si tronca in `parse`, non si butta.
    claims: list[str] = Field(default_factory=list, description="Gli id delle affermazioni, es. C12")


class ClaimMatching(BaseModel):
    model_config = ConfigDict(extra="forbid")

    matches: list[_ActivityMatch] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class Activity:
    element_id: str
    name: str


def prompt_version() -> str:
    from backend.llm.prompts import prompt_version as version

    return version("claim_matching", SYSTEM, json.dumps(ClaimMatching.model_json_schema(), sort_keys=True))


def render(activities: list[Activity], claims: list[SourceClaim]) -> str:
    lines = ["Attivita':"]
    lines += [f"[A{i}] {activity.name}" for i, activity in enumerate(activities)]
    lines.append("")
    lines.append("Affermazioni:")
    lines += [f"[C{claim.id}] {claim.statement[:MAX_STATEMENT_CHARS]}" for claim in claims]
    return "\n".join(lines)


def parse(result: ClaimMatching, activities: list[Activity], claims: list[SourceClaim]) -> dict[str, list[int]]:
    """Gli id delle affermazioni per elemento del BPMN, tenendo solo quelli mostrati."""
    shown = {claim.id for claim in claims}
    matched: dict[str, list[int]] = {}
    for item in result.matches:
        index = item.activity.strip().removeprefix("A")
        if not index.isdigit() or int(index) >= len(activities):
            continue
        element_id = activities[int(index)].element_id
        ids: list[int] = []
        for raw in item.claims:
            value = raw.strip().removeprefix("C")
            if value.isdigit() and int(value) in shown and int(value) not in ids:
                ids.append(int(value))
        if ids:
            matched.setdefault(element_id, [])
            matched[element_id] = (matched[element_id] + [i for i in ids if i not in matched[element_id]])[:MAX_PER_ACTIVITY]
    return matched


_cache: OrderedDict[str, dict[str, list[int]]] = OrderedDict()


def _cache_key(process_id: str, activities: list[Activity], claims: list[SourceClaim]) -> str:
    material = json.dumps(
        [process_id, [(a.element_id, a.name) for a in activities], [(c.id, c.statement) for c in claims]],
        ensure_ascii=False,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def match_with_llm(process_id: str, activities: list[Activity], claims: list[SourceClaim]) -> dict[str, list[int]]:
    """Le affermazioni che il modello abbina a ogni attivita', o ``{}`` se non puo'."""
    from backend.settings import settings

    if not activities or not claims or not settings.openai_api_key or settings.delir_fake_llm:
        return {}
    activities, claims = activities[:MAX_ACTIVITIES], claims[:MAX_CLAIMS]
    key = _cache_key(process_id, activities, claims)
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]

    from langchain_core.messages import HumanMessage, SystemMessage

    from backend.llm import LlmTask, OperationKind, operation, run

    user = render(activities, claims)
    try:
        with operation(OperationKind.CLAIM_MATCHING, process_id=process_id):
            result = run(
                task=LlmTask.CLAIM_MATCHING,
                messages=[SystemMessage(content=SYSTEM), HumanMessage(content=user)],
                output=ClaimMatching,
                input_characters=len(user),
                prompt_version=prompt_version(),
            )
    # Il ripiego non deve rompere il pannello: con qualunque guasto restano le proposte lessicali.
    except Exception:
        logger.warning("Abbinamento affermazioni con LLM non riuscito: solo proposte lessicali.", exc_info=True)
        return {}
    matched = parse(result, activities, claims)
    _cache[key] = matched
    if len(_cache) > _CACHE_SIZE:
        _cache.popitem(last=False)
    return matched


def proposals_from_llm(claim_ids: list[int], claims: list[SourceClaim], sources: dict[str, str]) -> list[ClaimProposal]:
    by_id = {claim.id: claim for claim in claims}
    return [
        ClaimProposal(
            claim_id=claim.id,
            statement=claim.statement,
            quote=claim.quote,
            quote_verified=claim.quote_verified,
            source_id=claim.source_id,
            source_name=sources.get(claim.source_id, claim.source_id),
            score=0.0,
            duration_hint=duration_hint(f"{claim.quote} {claim.statement}"),
            match="llm",
        )
        for claim in (by_id[i] for i in claim_ids if i in by_id)
    ]
