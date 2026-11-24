"""CAL-01: lo scenario FUZZY che SIMOD 5.2.1 ha scoperto sul log del dataset."""

from __future__ import annotations

import json
from pathlib import Path

FOLDER = (
    Path(__file__).resolve().parents[2] / "datasets" / "simod" / "discovered" / "Insurance_Claims_fuzzy"
)


def simod_fuzzy(*, until_midnight: bool = False) -> tuple[dict, str]:
    """Scenario e BPMN. ``until_midnight`` aggiunge al primo calendario una fascia
    lunedi' 23:00-mezzanotte al 40%, scritta come la scrive SIMOD: ``endTime`` "00:00:00"."""
    source = json.loads((FOLDER / "Insurance_Claims_fuzzy.json").read_text(encoding="utf-8"))
    bpmn = (FOLDER / "Insurance_Claims_fuzzy.bpmn").read_text(encoding="utf-8")
    if until_midnight:
        source["resource_calendars"][0]["time_periods"].append(
            {"from": "MONDAY", "to": "MONDAY", "beginTime": "23:00:00", "endTime": "00:00:00", "probability": 0.4}
        )
    return source, bpmn
