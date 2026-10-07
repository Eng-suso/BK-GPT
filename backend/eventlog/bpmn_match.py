"""Attivita' del log ed elementi del BPMN: cosa combacia e cosa resta scoperto.

Il suggerimento automatico accetta solo nomi identici dopo la normalizzazione
(maiuscole, accenti, spazi, punteggiatura). Due nomi diversi che "significano
la stessa cosa" sono un giudizio semantico (CODE_QUALITY: niente euristiche al
posto della semantica): li decide il consulente, o in futuro un suggerimento
LLM marcato come tale. I buchi si vedono da entrambi i lati: attivita' del log
senza elemento, elementi del modello che il log non osserva mai.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Literal

MatchReason = Literal["same_name", "ambiguous", "none"]


@dataclass(frozen=True, slots=True)
class ModelElement:
    element_id: str
    name: str


@dataclass(frozen=True, slots=True)
class ActivityMatch:
    activity: str
    events: int
    element_id: str | None
    reason: MatchReason


@dataclass(frozen=True, slots=True)
class MatchReport:
    matches: tuple[ActivityMatch, ...]
    unmatched_activities: tuple[str, ...]
    unobserved_elements: tuple[ModelElement, ...]

    def mapping(self) -> dict[str, str]:
        return {m.activity: m.element_id for m in self.matches if m.element_id}


def normalize(name: str) -> str:
    text = unicodedata.normalize("NFKD", name)
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    return re.sub(r"[\W_]+", " ", text).strip()


def suggest_matches(activity_counts: Counter[str], elements: list[ModelElement]) -> MatchReport:
    by_name: dict[str, list[ModelElement]] = {}
    for element in elements:
        by_name.setdefault(normalize(element.name or element.element_id), []).append(element)

    matches: list[ActivityMatch] = []
    for activity, count in sorted(activity_counts.items(), key=lambda item: (-item[1], item[0])):
        candidates = by_name.get(normalize(activity), [])
        if len(candidates) == 1:
            matches.append(ActivityMatch(activity, count, candidates[0].element_id, "same_name"))
        else:
            matches.append(ActivityMatch(activity, count, None, "ambiguous" if candidates else "none"))
    return report_for(matches, elements)


def apply_confirmed(
    activity_counts: Counter[str],
    elements: list[ModelElement],
    confirmed: dict[str, str | None],
) -> MatchReport:
    """Il mapping deciso dal consulente: attivita' -> elemento, o ``None`` per ignorarla."""
    known = {element.element_id for element in elements}
    unknown = sorted({element_id for element_id in confirmed.values() if element_id and element_id not in known})
    if unknown:
        raise ValueError(f"Elementi BPMN inesistenti nel mapping: {', '.join(unknown)}.")
    matches = [
        ActivityMatch(activity, count, confirmed.get(activity), "same_name" if confirmed.get(activity) else "none")
        for activity, count in sorted(activity_counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    return report_for(matches, elements)


def report_for(matches: list[ActivityMatch], elements: list[ModelElement]) -> MatchReport:
    observed = {m.element_id for m in matches if m.element_id}
    return MatchReport(
        matches=tuple(matches),
        unmatched_activities=tuple(m.activity for m in matches if m.element_id is None),
        unobserved_elements=tuple(e for e in elements if e.element_id not in observed),
    )
