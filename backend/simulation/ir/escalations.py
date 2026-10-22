"""Le escalation a tempo (SIM-35) compilate nel BPMN del motore.

Prosimos 2.1 non esegue i boundary event (spike G1). Il normalizer trasforma un
timer interrompente sul bordo di un'attivita' in una decisione dopo l'attivita'
(``bpmn_normalizer._timer_escalations``); qui la decisione diventa:

    -> [scade?] -> attivita' con durata <= T         -> percorso normale
                -> copia dell'attivita', lunga T     -> ramo d'escalation

La quota del secondo ramo e' la probabilita' che la durata superi T, calcolata
come il motore campiona: pix-framework scarta i valori fuori da [minimo,
massimo] e ricampiona, quindi la durata e' la distribuzione troncata. Per la
stessa ragione la durata del ramo normale e' la stessa distribuzione con il
massimo portato a T: e' esattamente la durata condizionata a non superarlo.

Un timer non interrompente (SIM-11g) e' gia' un ramo parallelo nel BPMN
normalizzato, che aspetta il timer e poi decide: qui riceve solo la quota, e
l'attivita' non cambia.

Approssimazioni dichiarate (``compatibility.py``):
- il timer conta la lavorazione, non l'attesa in coda davanti all'attivita';
- con piu' risorse sull'attivita' la quota e' la media fra le loro durate;
- il caso decide all'inizio se scadra': la quota e' giusta, il singolo caso no;
- una normale o un'esponenziale con la media oltre T non si tronca (la media
  uscirebbe dai limiti): i casi in tempo usano la durata intera.

Funzioni pure: il modello e il BPMN in ingresso non cambiano.
"""

from __future__ import annotations

import copy
import math
import xml.etree.ElementTree as ET

from defusedxml.ElementTree import fromstring as safe_fromstring

from backend.simulation.timers import timer_split_id
from backend.simulation.ir.model import (
    Activity,
    Assignment,
    Branch,
    Exponential,
    Fixed,
    Gamma,
    Gateway,
    LogNormal,
    Normal,
    SimulationModel,
    Uniform,
)

_BPMN = "http://www.omg.org/spec/BPMN/20100524/MODEL"


def expand_escalations(bpmn_xml: str, model: SimulationModel) -> tuple[str, SimulationModel]:
    """Il BPMN e il modello con le escalation a tempo compilate.

    Senza escalation restituisce gli stessi oggetti.
    """
    escalations = [gateway for gateway in model.gateways if gateway.escalation is not None]
    if not escalations:
        return bpmn_xml, model

    ET.register_namespace("", _BPMN)
    # Il BPMN viene dal consulente: letto senza entita' esterne ne' espansioni.
    root = safe_fromstring(bpmn_xml)
    taken = {element.get("id") for element in root.iter() if element.get("id")}
    activities = {activity.element_id: activity for activity in model.activities}
    gateways = [gateway for gateway in model.gateways if gateway.escalation is None]
    extra: list[Activity] = []
    updates = list(model.attribute_updates)
    for gateway in escalations:
        escalation = gateway.escalation
        assert escalation is not None
        activity = activities[escalation.activity_id]
        share = exceed_share(activity, escalation.after_seconds)
        if not escalation.interrupting:
            # SIM-11g: il ramo del timer ha gia' aspettato; l'attivita' resta com'e'.
            gateways.append(gateway.model_copy(update={"branches": tuple(
                branch.model_copy(update={"probability": 1 - share if branch.flow_id == escalation.normal_flow_id else share})
                for branch in gateway.branches
            )}))
            continue
        normal, timed_out = _split(activity, escalation.after_seconds, share)
        split = _rewrite(root, gateway, taken)
        activities[activity.element_id] = normal
        extra.append(timed_out)
        gateways.append(Gateway(element_id=split, branches=(
            Branch(flow_id=f"{split}__{activity.element_id}", probability=1 - share),
            Branch(flow_id=f"{split}__{timed_out.element_id}", probability=share),
        )))
        # La copia e' la stessa attivita': chi la completa riceve gli stessi aggiornamenti.
        updates.extend(
            update.model_copy(update={"element_id": timed_out.element_id})
            for update in model.attribute_updates
            if update.element_id == activity.element_id
        )

    expanded = model.model_copy(update={
        "activities": (*(activities[a.element_id] for a in model.activities), *extra),
        "gateways": tuple(gateways),
        "attribute_updates": tuple(updates),
    })
    xml = ET.tostring(root, encoding="unicode")
    # Rivalidato: un id generato che collide con uno esistente deve fallire qui, non nel motore.
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml, SimulationModel.model_validate(expanded.model_dump())


def exceed_share(activity: Activity, after_seconds: float) -> float:
    """La quota dei casi la cui lavorazione supera ``after_seconds``: media fra le risorse."""
    shares = [exceed_probability(assignment.duration, after_seconds) for assignment in activity.assignments]
    return sum(shares) / len(shares)


def exceed_probability(distribution, after: float) -> float:
    """P(durata > ``after``) per la distribuzione come la campiona il motore.

    pix-framework scarta i valori negativi o fuori da [minimo, massimo]: la
    probabilita' e' quella della distribuzione troncata.
    """
    if isinstance(distribution, Fixed):
        return 1.0 if distribution.value > after else 0.0
    low, high = max(0.0, distribution.minimum), distribution.maximum
    if after >= high:
        return 0.0
    if after < low:
        return 1.0
    cdf = _cdf(distribution)
    mass = cdf(high) - cdf(low)
    if mass <= 0:
        # Tutta la massa fuori dai limiti: il motore ripiega su un valore fisso.
        return 0.0
    return min(1.0, max(0.0, (cdf(high) - cdf(after)) / mass))


def _cdf(distribution):
    if isinstance(distribution, Uniform):
        lo, hi = distribution.minimum, distribution.maximum
        return lambda x: min(1.0, max(0.0, (x - lo) / (hi - lo)))
    if isinstance(distribution, Exponential):
        # pix-framework: loc = minimo, scala = media - minimo.
        loc, scale = distribution.minimum, distribution.mean - distribution.minimum
        return lambda x: 0.0 if x <= loc else 1.0 - math.exp(-(x - loc) / scale)
    if isinstance(distribution, Normal):
        mean, std = distribution.mean, distribution.std
        return lambda x: 0.5 * (1.0 + math.erf((x - mean) / (std * math.sqrt(2.0))))
    if isinstance(distribution, LogNormal):
        # pix-framework: media e varianza della lognormale, loc = 0.
        mean, variance = distribution.mean, distribution.variance
        sigma = math.sqrt(math.log(1.0 + variance / mean**2))
        mu = math.log(mean) - sigma**2 / 2.0
        return lambda x: 0.0 if x <= 0 else 0.5 * (1.0 + math.erf((math.log(x) - mu) / (sigma * math.sqrt(2.0))))
    if isinstance(distribution, Gamma):
        # pix-framework: forma = media^2 / varianza, scala = varianza / media, loc = 0.
        shape, scale = distribution.mean**2 / distribution.variance, distribution.variance / distribution.mean
        return lambda x: 0.0 if x <= 0 else _lower_gamma_regularized(shape, x / scale)
    raise TypeError(f"distribuzione senza funzione di ripartizione: {distribution!r}")  # pragma: no cover


def _lower_gamma_regularized(a: float, x: float) -> float:
    """P(a, x), con la serie per x < a + 1 e la frazione continua altrimenti (Numerical Recipes 6.2)."""
    if x <= 0:
        return 0.0
    log_prefix = a * math.log(x) - x - math.lgamma(a)
    if x < a + 1:
        term = total = 1.0 / a
        n = a
        for _ in range(500):
            n += 1
            term *= x / n
            total += term
            if abs(term) < abs(total) * 1e-12:
                break
        return min(1.0, total * math.exp(log_prefix))
    tiny = 1e-300
    b = x + 1 - a
    c, d = 1 / tiny, 1 / b
    h = d
    for i in range(1, 500):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = tiny if abs(d) < tiny else d
        c = b + an / c
        c = tiny if abs(c) < tiny else c
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < 1e-12:
            break
    return max(0.0, 1.0 - math.exp(log_prefix) * h)


def _split(activity: Activity, after: float, share: float) -> tuple[Activity, Activity]:
    """L'attivita' per i casi che finiscono in tempo, e la sua copia per quelli che scadono."""
    normal = activity
    if 0 < share < 1:
        normal = activity.model_copy(update={"assignments": tuple(
            assignment.model_copy(update={"duration": _capped(assignment.duration, after)})
            for assignment in activity.assignments
        )})
    timed_out = Activity(
        element_id=f"{activity.element_id}__timeout",
        name=activity.name,
        assignments=tuple(
            Assignment(resource_id=assignment.resource_id, duration=Fixed(value=after), provenance=assignment.provenance)
            for assignment in activity.assignments
        ),
    )
    return normal, timed_out


def _capped(distribution, after: float):
    """La stessa distribuzione con il massimo a ``after``, se lo supera e resta sopra il minimo."""
    if isinstance(distribution, Fixed) or distribution.maximum <= after or after <= distribution.minimum:
        return distribution
    capped = distribution.model_copy(update={"maximum": after})
    # La media dichiarata deve restare dentro i limiti nuovi per la validazione dell'IR.
    if isinstance(distribution, (Exponential, Normal)) and not distribution.minimum < distribution.mean < after:
        return distribution
    return type(distribution).model_validate(capped.model_dump())


def _rewrite(root: ET.Element, gateway: Gateway, taken: set[str]) -> str:
    """Toglie la decisione dopo l'attivita' e mette la scelta davanti, con la copia."""
    escalation = gateway.escalation
    assert escalation is not None
    process, task = _find(root, escalation.activity_id)
    _, decision = _find(root, gateway.element_id)
    split_id = _claim(taken, timer_split_id(escalation.activity_id))
    copy_id = _claim(taken, f"{escalation.activity_id}__timeout")
    flows = process.findall(f"{{{_BPMN}}}sequenceFlow")
    for flow in flows:
        if flow.get("targetRef") == escalation.activity_id:
            flow.set("targetRef", split_id)
    for flow in flows:
        if flow.get("sourceRef") == escalation.activity_id and flow.get("targetRef") == gateway.element_id:
            process.remove(flow)
        elif flow.get("sourceRef") == gateway.element_id:
            normal = flow.get("id") == escalation.normal_flow_id
            flow.set("sourceRef", escalation.activity_id if normal else copy_id)
    process.remove(decision)

    process.insert(list(process).index(task), ET.Element(f"{{{_BPMN}}}exclusiveGateway", {"id": split_id}))
    timed_out = copy.deepcopy(task)
    timed_out.set("id", copy_id)
    # La copia subito dopo l'originale: il nome nel log si riconduce all'id originale.
    process.insert(list(process).index(task) + 1, timed_out)
    for target in (escalation.activity_id, copy_id):
        process.append(ET.Element(f"{{{_BPMN}}}sequenceFlow", {
            "id": _claim(taken, f"{split_id}__{target}"), "sourceRef": split_id, "targetRef": target,
        }))
    return split_id


def _claim(taken: set[str], element_id: str) -> str:
    if element_id in taken:
        raise ValueError(f"il BPMN contiene già l'id {element_id}: rinomina quell'elemento per simulare l'escalation")
    taken.add(element_id)
    return element_id


def _find(root: ET.Element, element_id: str) -> tuple[ET.Element, ET.Element]:
    for process in root.iter(f"{{{_BPMN}}}process"):
        for child in process:
            if child.get("id") == element_id:
                return process, child
    raise ValueError(f"l'elemento {element_id} non è nel BPMN")
