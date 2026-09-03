"""Data perspective: data objects, data stores and their associations.

BPMN's data perspective (OMG 2.0 §10.4) is what makes a diagram say *which*
document each activity needs and produces. DeliR carries that in
`ProcessUnderstanding` across `data_objects`, `document_requirements`,
`input_outputs` and per-step `inputs` / `outputs`; this module reconciles those
into `BPMNDataObject` / `BPMNDataStore` records plus the `BPMNAssociation` edges
that dock them to the activities that read or write them.

Pure functions over the source model plus the compiled step->node map.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from backend.bpmn._helpers import json_documentation, source_ref_id, xml_id
from backend.bpmn.models import BPMNAssociation, BPMNDataObject, BPMNDataStore
from backend.process_understanding import ProcessUnderstanding

# ProcessDataObject.kind values that model a persistent system of record rather
# than a transient artifact.
_DATA_STORE_KINDS = frozenset({"record"})


@dataclass
class DataFlowResult:
    data_objects: list[BPMNDataObject] = field(default_factory=list)
    data_stores: list[BPMNDataStore] = field(default_factory=list)
    associations: list[BPMNAssociation] = field(default_factory=list)


def _norm(value: str | None) -> str:
    """Normalize a label by case-folding it and collapsing surrounding and repeated whitespace."""
    return " ".join((value or "").casefold().split())


def build_data_flow(
    process: ProcessUnderstanding,
    *,
    step_node_by_original_id: dict[str, str],
    used_ids: set[str],
) -> DataFlowResult:
    """
    Compile process data declarations and artifact usage into BPMN data objects, data stores, and associations.
    
    Parameters:
    	process (ProcessUnderstanding): Process definition containing data declarations, document requirements, and artifact usage.
    	step_node_by_original_id (dict[str, str]): Mapping from process step identifiers to generated BPMN activity node IDs.
    	used_ids (set[str]): Existing XML IDs reserved for collision-free generated identifiers.
    
    Returns:
    	DataFlowResult: Generated BPMN data objects, data stores, and associations.
    """
    usage = _artifact_usage(process, step_node_by_original_id)
    result = DataFlowResult()
    seen: set[str] = set()

    for index, item in enumerate(process.data_objects, start=1):
        key = _norm(item.label)
        seen.add(key)
        refs = [source_ref_id("data_objects", item.id)]
        doc = json_documentation(
            "data_object", {"kind": item.kind, "source_evidence": item.source_evidence}
        )
        use = usage.get(key)
        producer = next(iter(sorted(use["out"])), None) if use else None
        if item.kind in _DATA_STORE_KINDS:
            node_id = xml_id(item.id or f"DataStore_{index}", "DataStore", used_ids)
            result.data_stores.append(
                BPMNDataStore(
                    id=node_id, name=item.label, sourceNodeRef=producer, documentation=doc, sourceRefs=refs
                )
            )
        else:
            node_id = xml_id(item.id or f"DataObject_{index}", "DataObject", used_ids)
            result.data_objects.append(
                BPMNDataObject(
                    id=node_id,
                    name=item.label,
                    kind=item.kind,
                    sourceNodeRef=producer,
                    documentation=doc,
                    sourceRefs=refs,
                )
            )
        _wire(result.associations, node_id, use, used_ids)

    for requirement in process.document_requirements:
        key = _norm(requirement.label)
        if key in seen:
            continue
        seen.add(key)
        node_id = xml_id(requirement.id or requirement.label, "DataObject", used_ids)
        use = usage.get(key)
        result.data_objects.append(
            BPMNDataObject(
                id=node_id,
                name=requirement.label,
                kind="document",
                sourceNodeRef=next(iter(sorted(use["out"])), None) if use else None,
                documentation=json_documentation(
                    "document_requirement",
                    {
                        "required_when": requirement.required_when,
                        "mandatory": requirement.mandatory,
                        "provided_by_actor_id": requirement.provided_by_actor_id,
                        "received_by_actor_id": requirement.received_by_actor_id,
                    },
                ),
                sourceRefs=[source_ref_id("document_requirements", requirement.id)],
            )
        )
        _wire(result.associations, node_id, use, used_ids)

    for key, use in usage.items():
        if not key or key in seen or not (use["in"] or use["out"]):
            continue
        seen.add(key)
        node_id = xml_id(key or "DataObject", "DataObject", used_ids)
        result.data_objects.append(
            BPMNDataObject(
                id=node_id,
                name=key[:1].upper() + key[1:],
                kind="data",
                sourceNodeRef=next(iter(sorted(use["out"])), None),
                sourceRefs=[source_ref_id("input_outputs", key)],
            )
        )
        _wire(result.associations, node_id, use, used_ids)

    return result


def _artifact_usage(
    process: ProcessUnderstanding,
    step_node_by_original_id: dict[str, str],
) -> dict[str, dict[str, set[str]]]:
    """
    Map normalized artifact labels to their consuming and producing activity node IDs.
    
    Parameters:
        process (ProcessUnderstanding): Process definition containing steps and input/output declarations.
        step_node_by_original_id (dict[str, str]): Mapping from original step IDs to activity node IDs.
    
    Returns:
        dict[str, dict[str, set[str]]]: Artifact usage keyed by normalized label, with ``"in"`` for consumers and ``"out"`` for producers.
    """
    usage: dict[str, dict[str, set[str]]] = defaultdict(lambda: {"in": set(), "out": set()})

    node_by_step_key: dict[str, str] = {}
    for step in process.steps:
        node = step_node_by_original_id.get(step.id)
        if node is None:
            continue
        node_by_step_key[_norm(step.id)] = node
        node_by_step_key[_norm(step.label)] = node
        for label in step.inputs:
            usage[_norm(label)]["in"].add(node)
        for label in step.outputs:
            usage[_norm(label)]["out"].add(node)

    for item in process.input_outputs:
        node = node_by_step_key.get(_norm(item.step))
        if node is None:
            continue
        for label in item.input:
            usage[_norm(label)]["in"].add(node)
        for label in item.output:
            usage[_norm(label)]["out"].add(node)

    return usage


def _wire(
    associations: list[BPMNAssociation],
    data_id: str,
    use: dict[str, set[str]] | None,
    used_ids: set[str],
) -> None:
    """Connect a data element to its producing and consuming activities.
    
    Parameters:
    	associations (list[BPMNAssociation]): Collection to which the generated associations are appended.
    	data_id (str): Identifier of the data element.
    	use (dict[str, set[str]] | None): Producer and consumer activity identifiers.
    	used_ids (set[str]): Identifiers reserved for generated BPMN elements.
    """
    if not use:
        return
    for producer in sorted(use["out"]):
        associations.append(
            BPMNAssociation(
                id=xml_id(f"DataOut_{producer}_{data_id}", "Association", used_ids),
                sourceRef=producer,
                targetRef=data_id,
                direction="one",
            )
        )
    for consumer in sorted(use["in"]):
        associations.append(
            BPMNAssociation(
                id=xml_id(f"DataIn_{data_id}_{consumer}", "Association", used_ids),
                sourceRef=data_id,
                targetRef=consumer,
                direction="one",
            )
        )
