"""Uno scenario come patch sulla baseline (SIM-37).

Una patch dice solo cio' che cambia rispetto al modello di partenza: "Approvers
2 -> 3" e' un pool sostituito, non un modello intero da ricopiare. Le sezioni
con un identificativo (calendari, pool, attivita', gateway) si sostituiscono o
si aggiungono per id; quelle senza (attributi del caso, aggiornamenti, priorita')
si sostituiscono per intero quando la patch le indica. Il risultato e' di nuovo
un ``SimulationModel`` validato: una patch che rompe un riferimento fallisce qui,
non nel motore.
"""

from __future__ import annotations

from typing import TypeVar

from pydantic import Field, model_validator

from backend.simulation.ir.model import (
    Activity,
    Arrival,
    AttributeUpdate,
    Calendar,
    CaseAttribute,
    Gateway,
    PriorityRule,
    ResourcePool,
    SimulationModel,
    _Strict,
    _unique,
)

_T = TypeVar("_T")


class ModelPatch(_Strict):
    """Le differenze di uno scenario rispetto alla baseline."""

    arrival: Arrival | None = None
    calendars: tuple[Calendar, ...] = ()
    pools: tuple[ResourcePool, ...] = ()
    activities: tuple[Activity, ...] = ()
    gateways: tuple[Gateway, ...] = ()
    case_attributes: tuple[CaseAttribute, ...] | None = None
    attribute_updates: tuple[AttributeUpdate, ...] | None = None
    priority_rules: tuple[PriorityRule, ...] | None = None
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _no_duplicates(self):
        # Due voci con lo stesso id: quale vince? Meglio rifiutare che scegliere in silenzio.
        _unique("calendario nella patch", [c.id for c in self.calendars])
        _unique("pool nella patch", [p.id for p in self.pools])
        _unique("attivita' nella patch", [a.element_id for a in self.activities])
        _unique("gateway nella patch", [g.element_id for g in self.gateways])
        return self


def apply_patch(baseline: SimulationModel, patch: ModelPatch) -> SimulationModel:
    """La baseline con la patch applicata, validata come un modello nuovo."""
    return SimulationModel(
        arrival=patch.arrival or baseline.arrival,
        calendars=_upsert(baseline.calendars, patch.calendars, lambda c: c.id),
        pools=_upsert(baseline.pools, patch.pools, lambda p: p.id),
        activities=_upsert(baseline.activities, patch.activities, lambda a: a.element_id),
        gateways=_upsert(baseline.gateways, patch.gateways, lambda g: g.element_id),
        case_attributes=_replace(baseline.case_attributes, patch.case_attributes),
        attribute_updates=_replace(baseline.attribute_updates, patch.attribute_updates),
        priority_rules=_replace(baseline.priority_rules, patch.priority_rules),
    )


def _upsert(current: tuple[_T, ...], changes: tuple[_T, ...], key) -> tuple[_T, ...]:
    # L'ordine della baseline resta: il JSON compilato cambia solo dove cambia il modello.
    replaced = {key(item): item for item in changes}
    merged = [replaced.pop(key(item), item) for item in current]
    merged.extend(item for item in changes if key(item) in replaced)
    return tuple(merged)


def _replace(current: tuple[_T, ...], change: tuple[_T, ...] | None) -> tuple[_T, ...]:
    return current if change is None else change
