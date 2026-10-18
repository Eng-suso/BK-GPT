"""L'obiettivo di servizio (SLA) di uno scenario e il suo esito sul run (SIM-13).

Il consulente dice "il caso si chiude entro X per almeno il Y% dei casi". Il
motore non lo conosce: e' una misura sul log, con la stessa definizione di
cycle time dei KPI (ultima fine - prima abilitazione del caso).

SIM-13b: un gruppo di casi puo' avere un obiettivo suo ("premium entro 24
ore"). Il gruppo si riconosce dal valore dell'attributo del caso, che il motore
scrive su ogni riga del log.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from backend.schemas.simulation import SimSlaSegment
from backend.simulation.horizon import within_horizon
from backend.simulation.log_processor import after_warmup, parse_prosimos_log


@dataclass(frozen=True, slots=True)
class SlaOutcome:
    """L'esito dell'obiettivo sul run, come lo salva il riepilogo."""

    target_seconds: float
    share_target: float
    # Quota esatta: ``met`` e la percentuale mostrata non devono contraddirsi.
    share_within: float
    cases: int
    late_cases: int
    met: bool
    segments: tuple[SegmentOutcome, ...] = ()


@dataclass(frozen=True, slots=True)
class SegmentOutcome:
    """L'esito dell'obiettivo di un gruppo di casi (SIM-13b): ``attribute`` = ``value``."""

    attribute: str
    value: str
    target_seconds: float
    share_target: float
    share_within: float
    cases: int
    late_cases: int
    met: bool


@dataclass(frozen=True, slots=True)
class _Case:
    cycle: float
    attributes: dict[str, str]


def sla_outcome(
    log_csv: str,
    *,
    target_seconds: float,
    share: float,
    warmup_cases: int = 0,
    segments: Sequence[SimSlaSegment] = (),
    horizon: tuple[float, int] | None = None,
) -> SlaOutcome | None:
    """Quanti casi completati stanno nel target, e se l'obiettivo e' rispettato.

    ``None`` se il log non ha casi: senza casi non c'e' niente da giudicare.
    """
    cases = _cases(log_csv, warmup_cases, horizon)
    if not cases:
        return None
    within = _within(cases, target_seconds)
    return SlaOutcome(
        target_seconds=target_seconds,
        share_target=share,
        share_within=within / len(cases),
        cases=len(cases),
        late_cases=len(cases) - within,
        met=within / len(cases) >= share,
        segments=tuple(_segment(cases, segment) for segment in segments),
    )


def _segment(cases: list[_Case], segment: SimSlaSegment) -> SegmentOutcome:
    """Un gruppo senza casi nel run resta nell'esito con zero casi: non si giudica."""
    group = [case for case in cases if case.attributes.get(segment.attribute) == segment.value]
    within = _within(group, segment.target_seconds)
    share_within = within / len(group) if group else 0.0
    return SegmentOutcome(
        attribute=segment.attribute,
        value=segment.value,
        target_seconds=segment.target_seconds,
        share_target=segment.share,
        share_within=share_within,
        cases=len(group),
        late_cases=len(group) - within,
        met=bool(group) and share_within >= segment.share,
    )


def _within(cases: list[_Case], target_seconds: float) -> int:
    return sum(1 for case in cases if case.cycle <= target_seconds)


def _cases(log_csv: str, warmup_cases: int, horizon: tuple[float, int] | None) -> list[_Case]:
    first_enable: dict[str, float] = {}
    last_end: dict[str, float] = {}
    attributes: dict[str, dict[str, str]] = {}
    events = parse_prosimos_log(log_csv)
    if horizon is not None:
        # Con un periodo, i casi completati entro la fine (SIM-03).
        events, _, _ = within_horizon(events, *horizon)
    # Gli stessi casi dei KPI: quelli del riscaldamento (SIM-03) non contano.
    for event in after_warmup(events, warmup_cases):
        first_enable[event.case_id] = min(first_enable.get(event.case_id, event.enable), event.enable)
        last_end[event.case_id] = max(last_end.get(event.case_id, event.end), event.end)
        # Un attributo del caso vale lo stesso su ogni evento: basta il primo che lo porta.
        known = attributes.setdefault(event.case_id, {})
        for name, value in event.attributes.items():
            known.setdefault(name, value)
    return [_Case(cycle=end - first_enable[case_id], attributes=attributes[case_id]) for case_id, end in last_end.items()]
