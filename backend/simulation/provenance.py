"""Scenario provenance — where every simulable element came from.

DeliR simulations are built on interview / process-discovery evidence, so the
consultant has to see *how well grounded* each scenario parameter is before
trusting a run. This module maps every task / branching gateway in the scenario
template back to the process-understanding artifact stored on the approved BPMN
review:

* an activity whose structure resolves to a discovered step  -> ``declared``
* a gateway whose split resolves to a decision                -> ``declared``, with
  confidence from that decision's ``outcome_details`` certainty
* anything the model invented                                 -> ``estimated``

The origin is the Simulation IR's five-level ``Provenance`` (SIM-07): there is
one provenance in DeliR, and this module only says which level discovery
reaches (SIM-38). A discovered step becomes an ``interview`` source reference.

It never invents numbers. Durations, rates and probabilities are not captured
during discovery; the frontend layers "did the consultant change this from its
default?" on top of the structural signal here to produce the readiness roll-up.
"""

from __future__ import annotations

from backend.schemas.simulation import (
    ParameterProvenance,
    ProvenanceRef,
    ScenarioElementProvenance,
    ScenarioProvenanceResponse,
    ScenarioTemplateResponse,
)
from backend.simulation.bpmn_normalizer import normalize_bpmn_for_prosimos
from backend.simulation.ir.model import Confidence, Provenance, SourceRef
from backend.simulation.scenario_builder import describe_scenario_template
from backend.workspace_database import get_bpmn_review


def build_scenario_provenance(
    *,
    bpmn_model_id: str,
    current_bpmn_xml: str | None,
    stored_bpmn_xml: str | None,
) -> ScenarioProvenanceResponse:
    bpmn_xml = (current_bpmn_xml or stored_bpmn_xml or "").strip()
    if not bpmn_xml:
        raise ValueError("Salva o genera un BPMN prima di configurare la simulazione.")

    template = describe_scenario_template(normalize_bpmn_for_prosimos(bpmn_xml))
    review = get_bpmn_review(bpmn_model_id, include_approved=True)
    return map_scenario_provenance(template, review)


def map_scenario_provenance(
    template: ScenarioTemplateResponse,
    review: dict | None,
) -> ScenarioProvenanceResponse:
    """Pure mapping — template elements + an (optional) BPMN review dict ->
    per-element provenance. No IO, so it is the unit-test seam."""
    if review is None:
        return ScenarioProvenanceResponse(
            has_discovery=False,
            elements=[
                *(
                    ScenarioElementProvenance(
                        element_id=task.element_id,
                        kind="activity",
                        name=task.name,
                        parameter="duration",
                        provenance=_estimated(),
                        confidence="low",
                    )
                    for task in template.tasks
                ),
                *(
                    ScenarioElementProvenance(
                        element_id=gateway.element_id,
                        kind="gateway",
                        name=gateway.name,
                        parameter="branching",
                        provenance=_estimated(),
                        confidence="low",
                        open_questions=len(gateway.branches),
                    )
                    for gateway in template.gateways
                ),
            ],
        )

    semantic = review.get("bpmn_semantic_model") or {}
    understanding = review.get("process_understanding") or {}
    nodes = semantic.get("flowNodes") or []

    node_by_id = {node.get("id"): node for node in nodes if node.get("id")}
    node_by_name: dict[str, dict] = {}
    for node in nodes:
        key = _norm(node.get("name"))
        if key and key not in node_by_name:
            node_by_name[key] = node

    steps_by_id = _by_id(understanding.get("steps"))
    decisions_by_id = _by_id(understanding.get("decisions"))
    steps_by_label = _by_label(understanding.get("steps"))
    decisions_by_label = _by_label(understanding.get("decisions"))
    confidence = understanding.get("confidence") or {}

    elements: list[ScenarioElementProvenance] = []

    for task in template.tasks:
        node = node_by_id.get(task.element_id) or node_by_name.get(_norm(task.name))
        # alternative-path activities compile without a sourceRef — fall back to
        # matching the discovered step by its label.
        step = _resolve(node, "steps", steps_by_id) or steps_by_label.get(
            _norm(node.get("name") if node else task.name)
        )
        if step is None:
            elements.append(
                ScenarioElementProvenance(
                    element_id=task.element_id,
                    kind="activity",
                    name=task.name,
                    parameter="duration",
                    provenance=_estimated(),
                    confidence="low",
                )
            )
            continue
        evidence = _clip(step.get("source_evidence"))
        elements.append(
            ScenarioElementProvenance(
                element_id=task.element_id,
                kind="activity",
                name=task.name,
                parameter="duration",
                provenance=_declared("steps", step, "high" if evidence else "medium"),
                confidence="high" if evidence else "medium",
                evidence=evidence,
                hint_ref=ProvenanceRef(
                    field="steps", id=step.get("id"), label=step.get("label")
                ),
            )
        )

    for gateway in template.gateways:
        node = node_by_id.get(gateway.element_id) or node_by_name.get(_norm(gateway.name))
        decision = _resolve(node, "decisions", decisions_by_id) or decisions_by_label.get(
            _norm(node.get("name") if node else gateway.name)
        )
        if decision is None:
            elements.append(
                ScenarioElementProvenance(
                    element_id=gateway.element_id,
                    kind="gateway",
                    name=gateway.name,
                    parameter="branching",
                    provenance=_estimated(),
                    confidence="low",
                    open_questions=len(gateway.branches),
                )
            )
            continue
        certainties = [
            (outcome.get("certainty") or "explicit")
            for outcome in (decision.get("outcome_details") or [])
        ]
        to_validate = sum(1 for value in certainties if value != "explicit")
        elements.append(
            ScenarioElementProvenance(
                element_id=gateway.element_id,
                kind="gateway",
                name=gateway.name,
                parameter="branching",
                provenance=_declared("decisions", decision, _gateway_confidence(certainties)),
                confidence=_gateway_confidence(certainties),
                evidence=_clip(decision.get("source_evidence")),
                open_questions=to_validate,
                hint_ref=ProvenanceRef(
                    field="decisions",
                    id=decision.get("id"),
                    label=decision.get("label"),
                ),
            )
        )

    return ScenarioProvenanceResponse(
        has_discovery=True,
        process_confidence=_literal(confidence.get("overall"), {"high", "medium", "low"}),
        readiness_score=_readiness_percent(review.get("readiness_score")),
        missing_information=_clip(review.get("missing_information"), limit=8),
        weak_points=_clip(confidence.get("weak_points"), limit=6),
        elements=elements,
    )


# --- provenance on the IR scale ---------------------------------------------


def _estimated() -> ParameterProvenance:
    """The model proposed the element; discovery never mentioned it."""
    return _schema(Provenance(origin="estimated", confidence="low"))


def _declared(field: str, item: dict, confidence: Confidence) -> ParameterProvenance:
    """Discovery grounds the element: an interview step or decision says so."""
    ident = str(item.get("id") or "").strip()
    sources = (
        (SourceRef(kind="interview", id=f"{field}:{ident}", label=item.get("label") or None),)
        if ident
        else ()
    )
    return _schema(Provenance(origin="declared", confidence=confidence, sources=sources))


def _schema(provenance: Provenance) -> ParameterProvenance:
    # Built through the IR so the IR's validation is the one that applies.
    return ParameterProvenance.model_validate(provenance.model_dump(mode="json"))


# --- helpers ---------------------------------------------------------------


def _norm(value: object) -> str:
    return " ".join(str(value or "").split()).casefold()


def _by_id(items: object) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for item in items or []:
        if isinstance(item, dict) and item.get("id"):
            out[str(item["id"])] = item
    return out


def _by_label(items: object) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for item in items or []:
        key = _norm(item.get("label")) if isinstance(item, dict) else ""
        if key and key not in out:
            out[key] = item
    return out


def _resolve(node: dict | None, field: str, by_id: dict[str, dict]) -> dict | None:
    if not node:
        return None
    for raw in node.get("sourceRefs") or []:
        prefix, _, ident = str(raw).partition(":")
        if prefix == field and ident and ident in by_id:
            return by_id[ident]
    return None


def _gateway_confidence(certainties: list[str]) -> Confidence:
    if not certainties:
        return "low"
    if all(value == "explicit" for value in certainties):
        return "high"
    if any(value == "assumption" for value in certainties):
        return "low"
    return "medium"


def _clip(values: object, *, limit: int = 3) -> list[str]:
    out: list[str] = []
    for value in values or []:
        clean = " ".join(str(value or "").split())
        if clean:
            out.append(clean[:280])
        if len(out) >= limit:
            break
    return out


def _literal(value: object, allowed: set[str]) -> str | None:
    return value if value in allowed else None


def _readiness_percent(score: object) -> int | None:
    """Discovery quality score is 1–10; expose it as 0–100 for the UI."""
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        return None
    return max(0, min(100, round(float(score) * 10)))
