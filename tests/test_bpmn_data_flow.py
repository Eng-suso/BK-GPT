from backend.bpmn.data_flow import build_data_flow
from backend.process_understanding import (
    ProcessDataObject,
    ProcessDocumentRequirement,
    ProcessInputOutput,
    ProcessStep,
    ProcessUnderstanding,
)


def _process(**kw) -> ProcessUnderstanding:
    base = {"title": "P"}
    base.update(kw)
    return ProcessUnderstanding(**base)


def test_record_kind_becomes_a_data_store_wired_to_producer_and_consumer():
    process = _process(
        steps=[
            ProcessStep(id="T1", label="Registra", outputs=["Anagrafica cliente"]),
            ProcessStep(id="T2", label="Consulta", inputs=["anagrafica cliente"]),
        ],
        sequence=["T1", "T2"],
        data_objects=[ProcessDataObject(id="D_A", label="Anagrafica cliente", kind="record")],
    )
    result = build_data_flow(
        process, step_node_by_original_id={"T1": "n1", "T2": "n2"}, used_ids=set()
    )
    assert [s.name for s in result.data_stores] == ["Anagrafica cliente"]
    assert result.data_objects == []
    store_id = result.data_stores[0].id
    pairs = {(a.sourceRef, a.targetRef) for a in result.associations}
    assert ("n1", store_id) in pairs  # output association
    assert (store_id, "n2") in pairs  # input association
    assert all(a.direction == "one" for a in result.associations)


def test_document_requirement_without_a_data_object_still_renders():
    process = _process(
        steps=[ProcessStep(id="T", label="Verifica documenti")],
        sequence=["T"],
        document_requirements=[
            ProcessDocumentRequirement(id="R1", label="Carta identita", required_when="sempre", mandatory=True)
        ],
    )
    result = build_data_flow(process, step_node_by_original_id={"T": "n"}, used_ids=set())
    assert [o.name for o in result.data_objects] == ["Carta identita"]
    assert result.data_objects[0].kind == "document"


def test_loose_step_output_is_materialised_and_named_data_object_is_not_duplicated():
    process = _process(
        steps=[
            ProcessStep(id="T1", label="Prepara"),
            ProcessStep(id="T2", label="Invia"),
        ],
        sequence=["T1", "T2"],
        input_outputs=[
            ProcessInputOutput(step="Prepara", output=["Bozza contratto"]),
            ProcessInputOutput(step="Invia", input=["Bozza contratto", "Modulo firmato"]),
        ],
        data_objects=[ProcessDataObject(id="D_B", label="Bozza contratto", kind="document")],
    )
    result = build_data_flow(
        process, step_node_by_original_id={"T1": "n1", "T2": "n2"}, used_ids=set()
    )
    names = sorted(o.name for o in result.data_objects)
    assert names == ["Bozza contratto", "Modulo firmato"]  # loose input materialised, no dup
    bozza = next(o for o in result.data_objects if o.name == "Bozza contratto")
    pairs = {(a.sourceRef, a.targetRef) for a in result.associations}
    assert ("n1", bozza.id) in pairs
    assert (bozza.id, "n2") in pairs


def test_artifact_never_referenced_by_a_compiled_step_is_dropped():
    process = _process(
        steps=[ProcessStep(id="T", label="Passo")],
        sequence=["T"],
        input_outputs=[ProcessInputOutput(step="Passo sconosciuto", output=["Fantasma"])],
    )
    result = build_data_flow(process, step_node_by_original_id={"T": "n"}, used_ids=set())
    assert result.data_objects == []
    assert result.associations == []
