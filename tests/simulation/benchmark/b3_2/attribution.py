"""B3.2: le attese attribuite messe nel simulatore (ricerca).

L'attribuzione delle attese per causa e' in ``waiting.py`` (pronta per il prodotto, solo libreria standard),
riesportata qui per il banco. Qui ci sono solo le parti per gli scenari di ricerca: la quota
del ritardo esterno da simulare (v1-v5, schede 3-3e di ``docs/vpt/LOG.md``), la scelta della
distribuzione per Prosimos e i timer nel BPMN. Solo libreria standard (LIC-01).
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Callable, Sequence

from tests.simulation.benchmark.b3_2.waiting import (  # una sola attribuzione
    CAUSES,
    BusyPeriods,
    Calendar,
    Execution,
    Waiting,
    attribute,
    concurrent_pairs,
    discover_calendars,
    enablements,
    merge_periods,
)

__all__ = [
    "CAUSES", "BusyPeriods", "Calendar", "Execution", "Waiting", "add_timers", "attribute", "concurrent_pairs",
    "discover_calendars", "enablements", "extraneous_delays", "fit_closest", "fit_duration", "merge_periods", "on_shift_plus",
]


# --------------------------------------------------------------------------- ritardi esterni per il simulatore


def extraneous_delays(executions: Sequence[Execution], waitings: Sequence[Waiting], *, min_share: float = 0.05,
                      measure: str | Callable[[dict[str, float]], float] = "extraneous", fit=None) -> dict[str, dict]:
    """Per attivita' la distribuzione del ritardo esterno (formato Prosimos ``event_distribution``).

    Si considerano le esecuzioni con l'abilitazione osservabile, zeri compresi; un'attivita'
    ha un timer se piu' del ``min_share`` delle sue esecuzioni ha un ritardo (la stessa regola
    del lavoro di Chapela-Campa e Dumas). Il ritardo e' la quota ``extraneous`` (il batching no:
    lo spiega la risorsa). ``measure="idle"`` (v2) tiene solo i secondi del ritardo con la risorsa
    libera e in orario: il resto lo rifa' il simulatore con le sue code e i suoi calendari;
    ``measure="on_shift"`` (v3) toglie solo il tempo fuori orario della risorsa; una funzione dei
    secondi dell'attesa sceglie da se' (v5: ``on_shift_plus(beta)``).
    """
    values: dict[str, list[float]] = defaultdict(list)
    for e, w in zip(executions, waitings, strict=True):
        if w.enabled is not None:
            values[e.activity].append(measure(w.seconds) if callable(measure) else w.seconds.get(measure, 0.0))
    delays = {}
    for activity, xs in values.items():
        if sum(x > 0 for x in xs) / len(xs) > min_share:
            delays[activity] = (fit or fit_duration)(xs)
    return delays


def on_shift_plus(beta: float) -> Callable[[dict[str, float]], float]:
    """v5: il ritardo in orario piu' ``beta`` volte il fuori orario dentro il ritardo esterno."""
    return lambda seconds: seconds.get("on_shift", 0.0) + beta * (seconds.get("extraneous", 0.0) - seconds.get("on_shift", 0.0))


def fit_duration(xs: Sequence[float]) -> dict:
    """Una distribuzione per Prosimos dai momenti: fissa, esponenziale o lognormale."""
    n = len(xs)
    mean = sum(xs) / n
    var = sum((x - mean) ** 2 for x in xs) / max(1, n - 1)
    low, high = min(xs), max(xs)
    if mean <= 0 or var ** 0.5 < 0.01 * mean:
        return {"distribution_name": "fix", "distribution_params": [{"value": round(mean, 3)}]}
    cv = var ** 0.5 / mean
    if 0.8 <= cv <= 1.25:
        return {"distribution_name": "expon",
                "distribution_params": [{"value": round(mean, 3)}, {"value": round(low, 3)}, {"value": round(high, 3)}]}
    return {"distribution_name": "lognorm",
            "distribution_params": [{"value": round(mean, 3)}, {"value": round(var, 3)}, {"value": round(low, 3)}, {"value": round(high, 3)}]}


def fit_closest(xs: Sequence[float], points: int = 200) -> dict:
    """La distribuzione per Prosimos piu' vicina al campione (distanza di Wasserstein sui quantili), v4.

    Candidate dai momenti come ``fit_duration``: fissa, esponenziale, normale, lognormale, uniforme,
    tutte troncate a ``[min, max]`` del campione come le campiona Prosimos (ricampiona fuori dai limiti).
    """
    from statistics import NormalDist

    data = sorted(xs)
    n = len(data)
    mean = sum(data) / n
    var = sum((x - mean) ** 2 for x in data) / max(1, n - 1)
    low, high = data[0], data[-1]
    if mean <= 0 or var ** 0.5 < 0.01 * mean:
        return fit_duration(xs)
    std = var ** 0.5
    us = [(k + 0.5) / points for k in range(points)]
    empirical = [data[min(n - 1, int(u * n))] for u in us]
    unit = NormalDist()

    def truncated(ppf, cdf) -> list[float]:
        a, b = cdf(low), cdf(high)
        return [min(high, max(low, ppf(a + (b - a) * u))) for u in us]

    candidates: dict[str, tuple[list[float], dict]] = {}
    scale = mean - low
    if scale > 0:
        candidates["expon"] = (
            truncated(lambda q: low - scale * math.log(1 - min(q, 1 - 1e-12)), lambda x: 1 - math.exp(-(x - low) / scale)),
            {"distribution_name": "expon", "distribution_params": [_v(mean), _v(low), _v(high)]},
        )
    normal = NormalDist(mean, std)
    candidates["norm"] = (
        truncated(lambda q: normal.inv_cdf(min(max(q, 1e-12), 1 - 1e-12)), normal.cdf),
        {"distribution_name": "norm", "distribution_params": [_v(mean), _v(std), _v(low), _v(high)]},
    )
    sigma = math.sqrt(math.log(1 + var / mean**2))
    mu = math.log(mean) - sigma**2 / 2
    candidates["lognorm"] = (
        truncated(lambda q: math.exp(mu + sigma * unit.inv_cdf(min(max(q, 1e-12), 1 - 1e-12))),
                  lambda x: unit.cdf((math.log(x) - mu) / sigma) if x > 0 else 0.0),
        {"distribution_name": "lognorm", "distribution_params": [_v(mean), _v(var), _v(low), _v(high)]},
    )
    candidates["uniform"] = ([low + (high - low) * u for u in us],
                             {"distribution_name": "uniform", "distribution_params": [_v(low), _v(high)]})
    candidates["fix"] = ([mean] * points, {"distribution_name": "fix", "distribution_params": [_v(mean)]})
    best = min(candidates.values(), key=lambda c: sum(abs(a - b) for a, b in zip(c[0], empirical, strict=True)))
    return best[1]


def _v(x: float) -> dict:
    return {"value": round(x, 3)}


BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"


def add_timers(bpmn: str, delays: dict[str, dict]) -> tuple[str, list[dict]]:
    """Il BPMN con un timer prima di ogni attivita' con ritardo e la ``event_distribution`` dello scenario.

    Il timer prende il posto della freccia che entra nell'attivita' (una sola, come nei modelli
    di SIMOD); le attivita' con piu' frecce in ingresso restano senza timer.
    """
    import xml.etree.ElementTree as ET

    ET.register_namespace("", BPMN_NS)
    root = ET.fromstring(bpmn)
    q = lambda tag: f"{{{BPMN_NS}}}{tag}"  # noqa: E731
    process = root.find(q("process"))
    events = []
    for n, task in enumerate(process.findall(q("task"))):
        name = task.get("name")
        if name not in delays:
            continue
        incoming = [f for f in process.findall(q("sequenceFlow")) if f.get("targetRef") == task.get("id")]
        if len(incoming) != 1:
            continue
        timer_id, flow_id = f"Event_b32_{n}", f"Flow_b32_{n}"
        edge = incoming[0]
        edge.set("targetRef", timer_id)
        timer = ET.SubElement(process, q("intermediateCatchEvent"), {"id": timer_id})
        ET.SubElement(timer, q("incoming")).text = edge.get("id")
        ET.SubElement(timer, q("outgoing")).text = flow_id
        ET.SubElement(timer, q("timerEventDefinition"), {"id": f"TimerEventDefinition_b32_{n}"})
        ET.SubElement(process, q("sequenceFlow"), {"id": flow_id, "sourceRef": timer_id, "targetRef": task.get("id")})
        for inc in task.findall(q("incoming")):
            if inc.text == edge.get("id"):
                inc.text = flow_id
        events.append({"event_id": timer_id, "activity": name} | delays[name])
    return ET.tostring(root, encoding="unicode", xml_declaration=True), events
