from typing_extensions import Annotated
from typing import Literal

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

from backend import workspace_database
from backend.bpmn_semantic import BPMNSemanticModel, semantic_model_to_bpmn_xml
from backend.toolsets.common import format_workspace_result
from backend.workspace_services.bpmn_canvas_edit import (
    add_bpmn_element,
    clean_bpmn_visual_metadata_artifacts,
    clear_bpmn_process,
    connect_bpmn_elements,
    delete_bpmn_element,
    list_bpmn_elements,
    optimize_bpmn_layout,
    preview_bpmn_xml_change,
    reconnect_bpmn_flow,
    replace_bpmn_xml,
    update_bpmn_element,
    validate_bpmn_layout,
    validate_bpmn_xml,
)
from backend.workspace_services.bpmn_canvas_validation import validate_canvas_against_process
from backend.workspace_services.canvas_business_report import (
    canvas_business_report,
    construction_business_report,
)


CanvasBpmnOperation = Literal[
    "inspect",
    "list_elements",
    "update_element",
    "add_element",
    "delete_element",
    "clear_canvas",
    "connect_elements",
    "reconnect_flow",
    "layout",
    "validate_layout",
    "validate",
    "preview_change",
    "replace_xml",
    "list_versions",
    "restore_version",
]

CanvasConstructionOperation = Literal[
    "prepare_plan",
    "generate_preview",
    "validate_preview",
    "compare_with_current",
    "apply_approved_preview",
]

CanvasValidationOperation = Literal[
    "xml_validation",
    "semantic_validation",
    "readiness_validation",
    "traceability_validation",
    "full_report",
]


def _state_or_saved_canvas_xml(bpmn_model_id: str, state: dict) -> tuple[str, str]:
    state_xml = state.get("effective_bpmn_xml") or state.get("current_bpmn_xml")
    if state_xml:
        return str(state_xml), str(state.get("effective_bpmn_xml_source") or "live_canvas")

    model = workspace_database.get_bpmn_model(bpmn_model_id)
    if model is None:
        raise ValueError(f"Modello BPMN non trovato: {bpmn_model_id}")
    if not model["xml"]:
        raise ValueError("Il canvas non contiene ancora XML BPMN.")

    return model["xml"], "saved_backend"


def _saved_canvas_model_payload(bpmn_model_id: str) -> dict:
    model = workspace_database.get_bpmn_model(bpmn_model_id)
    if model is None:
        raise ValueError(f"Modello BPMN non trovato: {bpmn_model_id}")

    return {
        "id": model["id"],
        "process_id": model["process_id"],
        "name": model["name"],
        "has_xml": bool(model["xml"]),
        "xml": model["xml"] or "",
        "source": "saved_backend",
    }


def _canonical_semantic_model(value: dict | BPMNSemanticModel | None) -> BPMNSemanticModel | None:
    if not value:
        return None
    model = value if isinstance(value, BPMNSemanticModel) else BPMNSemanticModel.model_validate(value)
    if not model.compilationPlan or not model.sourceProcessUnderstanding:
        raise ValueError("BPMNSemanticModel legacy rifiutato: manca il payload semantico canonicale.")
    return model


def _review_or_state_semantic_context(
    bpmn_model_id: str,
    state: dict,
) -> tuple[dict | None, dict | None, BPMNSemanticModel | None]:
    bpmn_semantic_model = state.get("bpmn_semantic_model")
    review = workspace_database.get_bpmn_review(bpmn_model_id, include_approved=True)

    if review and not bpmn_semantic_model:
        bpmn_semantic_model = review.get("bpmn_semantic_model")

    model = _canonical_semantic_model(bpmn_semantic_model)
    if model is None:
        return review, None, None

    return review, model.sourceProcessUnderstanding, model


def _semantic_model_to_xml_from_context(bpmn_model_id: str, state: dict) -> tuple[str, dict]:
    review, _process_understanding, bpmn_semantic_model = _review_or_state_semantic_context(bpmn_model_id, state)
    if not bpmn_semantic_model:
        raise ValueError("BPMNSemanticModel non disponibile per generare la preview canvas.")

    xml = semantic_model_to_bpmn_xml(bpmn_semantic_model)
    return xml, {
        "review_pending": review is not None,
        "semantic_model_id": bpmn_semantic_model.id,
        "semantic_node_count": len(bpmn_semantic_model.flowNodes),
        "semantic_flow_count": len(bpmn_semantic_model.sequenceFlows),
        "semantic_lane_count": len(bpmn_semantic_model.lanes),
        "model_warnings": bpmn_semantic_model.model_warnings,
    }


@tool
def manage_canvas_bpmn_model(
    bpmn_model_id: str,
    operation: CanvasBpmnOperation,
    state: Annotated[dict, InjectedState()],
    element_id: str | None = None,
    element_type: str | None = None,
    name: str | None = None,
    documentation: str | None = None,
    source_id: str | None = None,
    target_id: str | None = None,
    flow_id: str | None = None,
    proposed_xml: str | None = None,
    version_id: int | None = None,
    change_summary: str | None = None,
    confirm_structural_change: bool = False,
) -> str:
    """
    Unified BPMN canvas CRUD facade.

    Use this as the primary canvas operation tool instead of selecting many
    low-level BPMN edit tools directly. Patch/Edit agents should use local
    operations only: inspect, list_elements, update_element, add_element,
    delete_element, connect_elements, reconnect_flow, layout and validate.
    Structural replacement requires preview/approval and confirm_structural_change.
    """
    if operation == "inspect":
        model = workspace_database.get_bpmn_model(bpmn_model_id)
        if model is None:
            raise ValueError(f"Modello BPMN non trovato: {bpmn_model_id}")
        xml, source = _state_or_saved_canvas_xml(bpmn_model_id, state)
        return format_workspace_result(
            "Canvas BPMN gestito",
            {
                "operation": operation,
                "id": model["id"],
                "process_id": model["process_id"],
                "name": model["name"],
                "has_xml": bool(xml),
                "xml": xml,
                "source": source,
            },
        )

    if operation == "list_elements":
        xml, source = _state_or_saved_canvas_xml(bpmn_model_id, state)
        return format_workspace_result(
            "Canvas BPMN gestito",
            {
                "operation": operation,
                "bpmn_model_id": bpmn_model_id,
                "source": source,
                "elements": list_bpmn_elements(xml),
            },
        )

    if operation == "update_element":
        if not element_id:
            raise ValueError("element_id obbligatorio per update_element.")
        xml, source = _state_or_saved_canvas_xml(bpmn_model_id, state)
        updated_xml, change = update_bpmn_element(
            xml=xml,
            element_id=element_id,
            name=name,
            documentation=documentation,
        )
        model = workspace_database.update_bpmn_model(
            bpmn_model_id,
            updated_xml,
            change_summary=f"Aggiornato elemento BPMN {element_id}",
            source="canvas_facade_update",
        )
        if model is None:
            raise ValueError(f"Modello BPMN non trovato: {bpmn_model_id}")
        return format_workspace_result(
            "Canvas BPMN gestito",
            {
                "operation": operation,
                "bpmn_model_id": bpmn_model_id,
                "source": source,
                "change": change,
                "xml_saved": True,
            },
        )

    if operation == "add_element":
        if not element_type or not name:
            raise ValueError("element_type e name sono obbligatori per add_element.")
        xml, source = _state_or_saved_canvas_xml(bpmn_model_id, state)
        updated_xml, change = add_bpmn_element(
            xml=xml,
            element_type=element_type,
            name=name,
            element_id=element_id,
            documentation=documentation,
        )
        model = workspace_database.update_bpmn_model(
            bpmn_model_id,
            updated_xml,
            change_summary=f"Aggiunto elemento BPMN {change['id']}",
            source="canvas_facade_add",
        )
        if model is None:
            raise ValueError(f"Modello BPMN non trovato: {bpmn_model_id}")
        return format_workspace_result(
            "Canvas BPMN gestito",
            {
                "operation": operation,
                "bpmn_model_id": bpmn_model_id,
                "source": source,
                "change": change,
                "xml_saved": True,
            },
        )

    if operation == "delete_element":
        if not element_id:
            raise ValueError("element_id obbligatorio per delete_element.")
        xml, source = _state_or_saved_canvas_xml(bpmn_model_id, state)
        updated_xml, change = delete_bpmn_element(xml=xml, element_id=element_id)
        model = workspace_database.update_bpmn_model(
            bpmn_model_id,
            updated_xml,
            change_summary=f"Eliminato elemento BPMN {element_id}",
            source="canvas_facade_delete",
        )
        if model is None:
            raise ValueError(f"Modello BPMN non trovato: {bpmn_model_id}")
        return format_workspace_result(
            "Canvas BPMN gestito",
            {
                "operation": operation,
                "bpmn_model_id": bpmn_model_id,
                "source": source,
                "change": change,
                "xml_saved": True,
            },
        )

    if operation == "clear_canvas":
        xml, source = _state_or_saved_canvas_xml(bpmn_model_id, state)
        updated_xml, change = clear_bpmn_process(xml=xml)
        model = workspace_database.update_bpmn_model(
            bpmn_model_id,
            updated_xml,
            change_summary="Svuotato canvas BPMN",
            source="canvas_facade_clear",
        )
        if model is None:
            raise ValueError(f"Modello BPMN non trovato: {bpmn_model_id}")
        return format_workspace_result(
            "Canvas BPMN gestito",
            {
                "operation": operation,
                "bpmn_model_id": bpmn_model_id,
                "source": source,
                "change": change,
                "validation": validate_bpmn_xml(updated_xml),
                "xml_saved": True,
            },
        )

    if operation == "connect_elements":
        if not source_id or not target_id:
            raise ValueError("source_id e target_id sono obbligatori per connect_elements.")
        xml, source = _state_or_saved_canvas_xml(bpmn_model_id, state)
        updated_xml, change = connect_bpmn_elements(
            xml=xml,
            source_id=source_id,
            target_id=target_id,
            flow_id=flow_id,
            name=name,
        )
        model = workspace_database.update_bpmn_model(
            bpmn_model_id,
            updated_xml,
            change_summary=f"Collegati elementi BPMN {source_id} -> {target_id}",
            source="canvas_facade_connect",
        )
        if model is None:
            raise ValueError(f"Modello BPMN non trovato: {bpmn_model_id}")
        return format_workspace_result(
            "Canvas BPMN gestito",
            {
                "operation": operation,
                "bpmn_model_id": bpmn_model_id,
                "source": source,
                "change": change,
                "xml_saved": True,
            },
        )

    if operation == "reconnect_flow":
        if not flow_id:
            raise ValueError("flow_id obbligatorio per reconnect_flow.")
        xml, source = _state_or_saved_canvas_xml(bpmn_model_id, state)
        updated_xml, change = reconnect_bpmn_flow(
            xml=xml,
            flow_id=flow_id,
            source_id=source_id,
            target_id=target_id,
        )
        model = workspace_database.update_bpmn_model(
            bpmn_model_id,
            updated_xml,
            change_summary=f"Ricollegato flow BPMN {flow_id}",
            source="canvas_facade_reconnect",
        )
        if model is None:
            raise ValueError(f"Modello BPMN non trovato: {bpmn_model_id}")
        return format_workspace_result(
            "Canvas BPMN gestito",
            {
                "operation": operation,
                "bpmn_model_id": bpmn_model_id,
                "source": source,
                "change": change,
                "xml_saved": True,
            },
        )

    if operation == "layout":
        xml, source = _state_or_saved_canvas_xml(bpmn_model_id, state)
        updated_xml, layout_optimization = optimize_bpmn_layout(xml)
        layout_validation = layout_optimization.get("selected_report") or validate_bpmn_layout(updated_xml)
        model = workspace_database.update_bpmn_model(
            bpmn_model_id,
            updated_xml,
            change_summary="Layout BPMN aggiornato",
            source="canvas_facade_layout",
        )
        if model is None:
            raise ValueError(f"Modello BPMN non trovato: {bpmn_model_id}")
        return format_workspace_result(
            "Canvas BPMN gestito",
            {
                "operation": operation,
                "bpmn_model_id": bpmn_model_id,
                "source": source,
                "validation": validate_bpmn_xml(updated_xml),
                "layout_validation": layout_validation,
                "layout_optimization": layout_optimization,
                "xml_saved": True,
            },
        )

    if operation == "validate_layout":
        xml, source = _state_or_saved_canvas_xml(bpmn_model_id, state)
        return format_workspace_result(
            "Canvas BPMN gestito",
            {
                "operation": operation,
                "bpmn_model_id": bpmn_model_id,
                "source": source,
                **validate_bpmn_layout(xml),
            },
        )

    if operation == "validate":
        xml, source = _state_or_saved_canvas_xml(bpmn_model_id, state)
        return format_workspace_result(
            "Canvas BPMN gestito",
            {
                "operation": operation,
                "bpmn_model_id": bpmn_model_id,
                "source": source,
                **validate_bpmn_xml(xml),
            },
        )

    if operation == "preview_change":
        if not proposed_xml:
            raise ValueError("proposed_xml obbligatorio per preview_change.")
        current_xml, source = _state_or_saved_canvas_xml(bpmn_model_id, state)
        clean_proposed_xml = replace_bpmn_xml(proposed_xml)
        return format_workspace_result(
            "Canvas BPMN gestito",
            {
                "operation": operation,
                "bpmn_model_id": bpmn_model_id,
                "source": source,
                **preview_bpmn_xml_change(current_xml, clean_proposed_xml),
            },
        )

    if operation == "replace_xml":
        if not proposed_xml:
            raise ValueError("proposed_xml obbligatorio per replace_xml.")
        if not confirm_structural_change:
            raise ValueError("replace_xml richiede confirm_structural_change=True dopo preview/approvazione.")
        clean_xml = replace_bpmn_xml(proposed_xml)
        model = workspace_database.update_bpmn_model(
            bpmn_model_id,
            clean_xml,
            change_summary=change_summary or "Sostituzione strutturale canvas",
            source="canvas_facade_replace",
        )
        if model is None:
            raise ValueError(f"Modello BPMN non trovato: {bpmn_model_id}")
        return format_workspace_result(
            "Canvas BPMN gestito",
            {
                "operation": operation,
                "bpmn_model_id": bpmn_model_id,
                "change_summary": change_summary or "Sostituzione strutturale canvas",
                "xml_saved": True,
            },
        )

    if operation == "list_versions":
        return format_workspace_result(
            "Canvas BPMN gestito",
            {
                "operation": operation,
                "bpmn_model_id": bpmn_model_id,
                "versions": workspace_database.list_bpmn_versions(bpmn_model_id),
            },
        )

    if operation == "restore_version":
        if version_id is None:
            raise ValueError("version_id obbligatorio per restore_version.")
        return format_workspace_result(
            "Canvas BPMN gestito",
            {
                "operation": operation,
                **workspace_database.restore_bpmn_version(
                    bpmn_model_id=bpmn_model_id,
                    version_id=version_id,
                ),
            },
        )

    raise ValueError(f"Operazione canvas non supportata: {operation}")


@tool
def manage_canvas_construction(
    bpmn_model_id: str,
    operation: CanvasConstructionOperation,
    state: Annotated[dict, InjectedState()],
    objective: str,
    process_id: str | None = None,
    constraints: list[str] | None = None,
    proposed_xml: str | None = None,
    change_summary: str | None = None,
    confirm_apply: bool = False,
) -> str:
    """
    Structural canvas construction facade.

    Use for significant BPMN build/rebuild work. It starts from the loaded
    ProcessUnderstanding/BPMNSemanticModel or pending review, produces previews,
    compares with the current canvas and applies only after explicit approval.
    """
    review, process_understanding, bpmn_semantic_model = _review_or_state_semantic_context(bpmn_model_id, state)
    constraints = constraints or []

    if operation == "prepare_plan":
        semantic_model = BPMNSemanticModel.model_validate(bpmn_semantic_model) if bpmn_semantic_model else None
        missing_information = state.get("missing_information") or (review.get("missing_information") if review else [])
        payload = {
            "operation": operation,
            "bpmn_model_id": bpmn_model_id,
            "process_id": process_id or state.get("process_id"),
            "objective": objective,
            "source": "bpmn_semantic_model" if semantic_model else "missing_semantic_model",
            "reconstruction_scope": "full_model",
            "semantic_requirements": [
                f"{len(semantic_model.flowNodes)} flow nodes",
                f"{len(semantic_model.sequenceFlows)} sequence flows",
                f"{len(semantic_model.lanes)} lanes",
            ]
            if semantic_model
            else [],
            "unresolved_gaps": missing_information or [],
            "constraints": constraints,
            "requires_preview": True,
            "requires_user_approval": True,
            "warnings": [] if semantic_model else ["BPMNSemanticModel non disponibile."],
        }
        payload["business_report"] = construction_business_report(payload)
        return format_workspace_result(
            "Costruzione canvas BPMN",
            payload,
        )

    if operation == "generate_preview":
        xml, context = _semantic_model_to_xml_from_context(bpmn_model_id, state)
        xml, clean_report = clean_bpmn_visual_metadata_artifacts(xml)
        validation = validate_bpmn_xml(xml)
        payload = {
            "operation": operation,
            "bpmn_model_id": bpmn_model_id,
            "objective": objective,
            "proposed_xml": xml,
            "validation": validation,
            "context": context,
            "clean_report": clean_report,
            "constraints": constraints,
        }
        payload["business_report"] = construction_business_report(payload)
        return format_workspace_result(
            "Costruzione canvas BPMN",
            payload,
        )

    if operation == "validate_preview":
        xml = proposed_xml
        context = {}
        if not xml:
            xml, context = _semantic_model_to_xml_from_context(bpmn_model_id, state)
        xml, clean_report = clean_bpmn_visual_metadata_artifacts(xml)
        validation = validate_canvas_against_process(
            xml=xml,
            process_understanding=process_understanding,
            bpmn_semantic_model=bpmn_semantic_model,
        )
        payload = {
            "operation": operation,
            "bpmn_model_id": bpmn_model_id,
            "objective": objective,
            "validation": validation,
            "context": context,
            "clean_report": clean_report,
        }
        payload["business_report"] = construction_business_report(payload)
        return format_workspace_result(
            "Costruzione canvas BPMN",
            payload,
        )

    if operation == "compare_with_current":
        xml = proposed_xml
        context = {}
        if not xml:
            xml, context = _semantic_model_to_xml_from_context(bpmn_model_id, state)
        xml, clean_report = clean_bpmn_visual_metadata_artifacts(xml)
        current_xml, source = _state_or_saved_canvas_xml(bpmn_model_id, state)
        clean_proposed_xml = replace_bpmn_xml(xml)
        payload = {
            "operation": operation,
            "bpmn_model_id": bpmn_model_id,
            "objective": objective,
            "source": source,
            **preview_bpmn_xml_change(current_xml, clean_proposed_xml),
            "context": context,
            "clean_report": clean_report,
        }
        payload["business_report"] = construction_business_report(payload)
        return format_workspace_result(
            "Costruzione canvas BPMN",
            payload,
        )

    if operation == "apply_approved_preview":
        if not proposed_xml:
            raise ValueError("proposed_xml obbligatorio per apply_approved_preview.")
        if not confirm_apply:
            raise ValueError("apply_approved_preview richiede confirm_apply=True dopo preview e approvazione.")
        proposed_xml, clean_report = clean_bpmn_visual_metadata_artifacts(proposed_xml)
        validation = validate_canvas_against_process(
            xml=proposed_xml,
            process_understanding=process_understanding,
            bpmn_semantic_model=bpmn_semantic_model,
        )
        if validation.get("issues"):
            raise ValueError("Preview BPMN non applicata: validazione con issue bloccanti.")
        clean_xml = replace_bpmn_xml(proposed_xml)
        model = workspace_database.update_bpmn_model(
            bpmn_model_id,
            clean_xml,
            change_summary=change_summary or "Costruzione canvas BPMN approvata",
            source="canvas_construction_apply",
        )
        if model is None:
            raise ValueError(f"Modello BPMN non trovato: {bpmn_model_id}")
        return format_workspace_result(
            "Costruzione canvas BPMN",
            {
                "operation": operation,
                "bpmn_model_id": bpmn_model_id,
                "objective": objective,
                "validation": validation,
                "clean_report": clean_report,
                "business_report": construction_business_report(
                    {"operation": operation, "validation": validation}
                ),
                "xml_saved": True,
            },
        )

    raise ValueError(f"Operazione construction non supportata: {operation}")


@tool
def manage_canvas_validation(
    bpmn_model_id: str,
    operation: CanvasValidationOperation,
    state: Annotated[dict, InjectedState()],
    objective: str,
) -> str:
    """
    Canvas validation facade for technical and semantic BPMN quality checks.
    Use full_report before applying broad construction work or when the user asks
    whether the current canvas correctly represents the process.
    """
    xml, source = _state_or_saved_canvas_xml(bpmn_model_id, state)
    review, process_understanding, bpmn_semantic_model = _review_or_state_semantic_context(bpmn_model_id, state)

    if operation == "xml_validation":
        result = validate_bpmn_xml(xml)
    elif operation in {"semantic_validation", "full_report"}:
        result = validate_canvas_against_process(
            xml=xml,
            process_understanding=process_understanding,
            bpmn_semantic_model=bpmn_semantic_model,
        )
    elif operation == "readiness_validation":
        readiness_score = state.get("readiness_score")
        if readiness_score is None and review:
            readiness_score = review.get("readiness_score")
        missing_information = state.get("missing_information") or (review.get("missing_information") if review else [])
        result = {
            "valid": bool(readiness_score and readiness_score >= 7 and not missing_information),
            "readiness_score": readiness_score,
            "missing_information": missing_information or [],
            "warnings": [] if readiness_score and readiness_score >= 7 else ["Readiness sotto la soglia consigliata."],
        }
    elif operation == "traceability_validation":
        result = {
            "valid": bool(process_understanding and bpmn_semantic_model),
            "process_understanding_available": bool(process_understanding),
            "bpmn_semantic_model_available": bool(bpmn_semantic_model),
            "warnings": []
            if process_understanding and bpmn_semantic_model
            else ["Traceability limitata: ProcessUnderstanding o BPMNSemanticModel mancanti."],
        }
    else:
        raise ValueError(f"Operazione validation non supportata: {operation}")

    return format_workspace_result(
        "Validazione canvas BPMN",
        {
            "operation": operation,
            "bpmn_model_id": bpmn_model_id,
            "source": source,
            "objective": objective,
            "result": result,
            "business_report": canvas_business_report(result),
        },
    )


@tool
def read_canvas_bpmn_xml(
    bpmn_model_id: str,
    state: Annotated[dict, InjectedState()],
) -> str:
    """
    Read the current BPMN XML for an existing canvas model.
    Use in canvas scope when the user asks to inspect, read, explain, summarize,
    validate, or reason over the current BPMN XML shown in this canvas.
    Do not use this to generate new XML.
    """
    model = workspace_database.get_bpmn_model(bpmn_model_id)
    if model is None:
        raise ValueError(f"Modello BPMN non trovato: {bpmn_model_id}")

    xml, source = _state_or_saved_canvas_xml(bpmn_model_id, state)
    return format_workspace_result(
        "BPMN XML canvas",
        {
            "id": model["id"],
            "process_id": model["process_id"],
            "name": model["name"],
            "has_xml": bool(xml),
            "xml": xml,
            "source": source,
        },
    )


@tool
def read_process_bpmn_xml(process_id: str) -> str:
    """
    Read the saved BPMN XML for a process by resolving its BPMN model.
    Use in process scope when the user asks to inspect, read, explain, summarize,
    validate, or reason over the current BPMN XML for this process.
    Do not use this to generate new XML.
    """
    process = workspace_database.get_process(process_id)
    if process is None:
        raise ValueError(f"Processo non trovato: {process_id}")

    return format_workspace_result(
        "BPMN XML processo",
        _saved_canvas_model_payload(process["bpmn_model_id"]),
    )


@tool
def list_canvas_bpmn_elements(
    bpmn_model_id: str,
    state: Annotated[dict, InjectedState()],
) -> str:
    """
    List editable BPMN elements from the current canvas XML.
    Use before modifying an element when the user refers to an activity, gateway,
    event, lane, sequence flow, data object, or annotation but has not provided
    the exact BPMN element_id.
    """
    xml, source = _state_or_saved_canvas_xml(bpmn_model_id, state)
    return format_workspace_result(
        "Elementi BPMN canvas",
        {
            "bpmn_model_id": bpmn_model_id,
            "source": source,
            "elements": list_bpmn_elements(xml),
        },
    )


@tool
def update_canvas_bpmn_element(
    bpmn_model_id: str,
    element_id: str,
    state: Annotated[dict, InjectedState()],
    name: str | None = None,
    documentation: str | None = None,
) -> str:
    """
    Modify an existing BPMN element in the canvas and save the updated XML.
    Use for targeted edits such as renaming an activity/gateway/event/lane/flow
    or updating its documentation. This is deterministic XML editing, not free-form
    BPMN generation. If the element_id is unknown, call list_canvas_bpmn_elements first.
    """
    xml, source = _state_or_saved_canvas_xml(bpmn_model_id, state)
    updated_xml, change = update_bpmn_element(
        xml=xml,
        element_id=element_id,
        name=name,
        documentation=documentation,
    )
    model = workspace_database.update_bpmn_model(bpmn_model_id, updated_xml)
    if model is None:
        raise ValueError(f"Modello BPMN non trovato: {bpmn_model_id}")

    return format_workspace_result(
        "Elemento BPMN aggiornato",
        {
            "bpmn_model_id": bpmn_model_id,
            "source": source,
            "change": change,
            "xml_saved": True,
        },
    )


@tool
def add_canvas_bpmn_element(
    bpmn_model_id: str,
    element_type: str,
    name: str,
    state: Annotated[dict, InjectedState()],
    element_id: str | None = None,
    documentation: str | None = None,
) -> str:
    """
    Add one BPMN element to the current canvas and save the updated XML.
    Supported element_type values include startEvent, endEvent, task, userTask,
    serviceTask, manualTask, exclusiveGateway, parallelGateway, inclusiveGateway,
    lane, dataObjectReference and textAnnotation. Use semantic model terms to pick
    the correct BPMN type, then add a single element deterministically.
    """
    xml, source = _state_or_saved_canvas_xml(bpmn_model_id, state)
    updated_xml, change = add_bpmn_element(
        xml=xml,
        element_type=element_type,
        name=name,
        element_id=element_id,
        documentation=documentation,
    )
    model = workspace_database.update_bpmn_model(
        bpmn_model_id,
        updated_xml,
        change_summary=f"Aggiunto elemento BPMN {change['id']}",
        source="canvas_agent_add",
    )
    if model is None:
        raise ValueError(f"Modello BPMN non trovato: {bpmn_model_id}")

    return format_workspace_result(
        "Elemento BPMN aggiunto",
        {"bpmn_model_id": bpmn_model_id, "source": source, "change": change, "xml_saved": True},
    )


@tool
def delete_canvas_bpmn_element(
    bpmn_model_id: str,
    element_id: str,
    state: Annotated[dict, InjectedState()],
) -> str:
    """
    Delete one BPMN element from the current canvas and save the updated XML.
    If the element is a flow node, connected sequence flows are removed as well.
    Use list_canvas_bpmn_elements first when the exact element_id is uncertain.
    """
    xml, source = _state_or_saved_canvas_xml(bpmn_model_id, state)
    updated_xml, change = delete_bpmn_element(xml=xml, element_id=element_id)
    model = workspace_database.update_bpmn_model(
        bpmn_model_id,
        updated_xml,
        change_summary=f"Eliminato elemento BPMN {element_id}",
        source="canvas_agent_delete",
    )
    if model is None:
        raise ValueError(f"Modello BPMN non trovato: {bpmn_model_id}")

    return format_workspace_result(
        "Elemento BPMN eliminato",
        {"bpmn_model_id": bpmn_model_id, "source": source, "change": change, "xml_saved": True},
    )


@tool
def connect_canvas_bpmn_elements(
    bpmn_model_id: str,
    source_id: str,
    target_id: str,
    state: Annotated[dict, InjectedState()],
    flow_id: str | None = None,
    name: str | None = None,
) -> str:
    """
    Create a BPMN sequenceFlow between two existing flow nodes and save the XML.
    Use only for sequence flow connections. Use list_canvas_bpmn_elements first
    when source_id or target_id is uncertain.
    """
    xml, source = _state_or_saved_canvas_xml(bpmn_model_id, state)
    updated_xml, change = connect_bpmn_elements(
        xml=xml,
        source_id=source_id,
        target_id=target_id,
        flow_id=flow_id,
        name=name,
    )
    model = workspace_database.update_bpmn_model(
        bpmn_model_id,
        updated_xml,
        change_summary=f"Collegati elementi BPMN {source_id} -> {target_id}",
        source="canvas_agent_connect",
    )
    if model is None:
        raise ValueError(f"Modello BPMN non trovato: {bpmn_model_id}")

    return format_workspace_result(
        "Elementi BPMN collegati",
        {"bpmn_model_id": bpmn_model_id, "source": source, "change": change, "xml_saved": True},
    )


@tool
def reconnect_canvas_bpmn_flow(
    bpmn_model_id: str,
    flow_id: str,
    state: Annotated[dict, InjectedState()],
    source_id: str | None = None,
    target_id: str | None = None,
) -> str:
    """
    Change the source and/or target of an existing BPMN sequenceFlow and save XML.
    Use when the user asks to reroute an existing connection.
    """
    xml, source = _state_or_saved_canvas_xml(bpmn_model_id, state)
    updated_xml, change = reconnect_bpmn_flow(
        xml=xml,
        flow_id=flow_id,
        source_id=source_id,
        target_id=target_id,
    )
    model = workspace_database.update_bpmn_model(
        bpmn_model_id,
        updated_xml,
        change_summary=f"Ricollegato flow BPMN {flow_id}",
        source="canvas_agent_reconnect",
    )
    if model is None:
        raise ValueError(f"Modello BPMN non trovato: {bpmn_model_id}")

    return format_workspace_result(
        "Flow BPMN ricollegato",
        {"bpmn_model_id": bpmn_model_id, "source": source, "change": change, "xml_saved": True},
    )


@tool
def validate_canvas_bpmn(
    bpmn_model_id: str,
    state: Annotated[dict, InjectedState()],
) -> str:
    """
    Validate the current canvas BPMN XML before or after changes.
    Checks parseability, process presence, sequenceFlow references and basic
    renderability signals such as BPMN DI.
    """
    xml, source = _state_or_saved_canvas_xml(bpmn_model_id, state)
    return format_workspace_result(
        "Validazione BPMN canvas",
        {"bpmn_model_id": bpmn_model_id, "source": source, **validate_bpmn_xml(xml)},
    )


@tool
def preview_canvas_bpmn_change(
    bpmn_model_id: str,
    proposed_xml: str,
    state: Annotated[dict, InjectedState()],
) -> str:
    """
    Preview a large BPMN XML change before applying it.
    Use before replace_canvas_bpmn_xml when the change is broad, risky or generated
    from a semantic model. This tool does not save XML.
    """
    current_xml, source = _state_or_saved_canvas_xml(bpmn_model_id, state)
    clean_proposed_xml = replace_bpmn_xml(proposed_xml)
    return format_workspace_result(
        "Anteprima modifica BPMN",
        {
            "bpmn_model_id": bpmn_model_id,
            "source": source,
            **preview_bpmn_xml_change(current_xml, clean_proposed_xml),
        },
    )


@tool
def layout_canvas_bpmn(
    bpmn_model_id: str,
    state: Annotated[dict, InjectedState()],
) -> str:
    """
    Rebuild simple BPMN DI layout for the current XML and save it.
    Use when the diagram exists semantically but renders badly or has missing DI.
    This should not change BPMN semantics.
    """
    xml, source = _state_or_saved_canvas_xml(bpmn_model_id, state)
    updated_xml, layout_optimization = optimize_bpmn_layout(xml)
    layout_validation = layout_optimization.get("selected_report") or validate_bpmn_layout(updated_xml)
    model = workspace_database.update_bpmn_model(
        bpmn_model_id,
        updated_xml,
        change_summary="Layout BPMN aggiornato",
        source="canvas_agent_layout",
    )
    if model is None:
        raise ValueError(f"Modello BPMN non trovato: {bpmn_model_id}")

    return format_workspace_result(
        "Layout BPMN aggiornato",
        {
            "bpmn_model_id": bpmn_model_id,
            "source": source,
            "validation": validate_bpmn_xml(updated_xml),
            "layout_validation": layout_validation,
            "layout_optimization": layout_optimization,
            "xml_saved": True,
        },
    )


@tool
def replace_canvas_bpmn_xml(
    bpmn_model_id: str,
    xml: str,
    change_summary: str,
) -> str:
    """
    Replace the entire BPMN XML for the canvas after a deliberate model-level edit.
    Use only when targeted element editing is not enough and the XML comes from a
    validated BPMNSemanticModel or an explicit user-approved BPMN XML update.
    """
    clean_xml = replace_bpmn_xml(xml)
    model = workspace_database.update_bpmn_model(
        bpmn_model_id,
        clean_xml,
        change_summary=change_summary,
        source="canvas_agent_replace",
    )
    if model is None:
        raise ValueError(f"Modello BPMN non trovato: {bpmn_model_id}")

    return format_workspace_result(
        "Canvas BPMN sostituito",
        {
            "bpmn_model_id": bpmn_model_id,
            "change_summary": change_summary,
            "xml_saved": True,
        },
    )


@tool
def list_canvas_bpmn_versions(bpmn_model_id: str) -> str:
    """
    List saved BPMN versions for this canvas model.
    Use when the user asks for history, previous saves, or available restore points.
    """
    return format_workspace_result(
        "Cronologia BPMN canvas",
        {
            "bpmn_model_id": bpmn_model_id,
            "versions": workspace_database.list_bpmn_versions(bpmn_model_id),
        },
    )


@tool
def restore_canvas_bpmn_version(bpmn_model_id: str, version_id: int) -> str:
    """
    Restore one saved BPMN version and create a new restore version entry.
    Use only when the user explicitly asks to restore a specific version_id.
    """
    return format_workspace_result(
        "Versione BPMN ripristinata",
        workspace_database.restore_bpmn_version(
            bpmn_model_id=bpmn_model_id,
            version_id=version_id,
        ),
    )


@tool
def prepare_canvas_bpmn_review(bpmn_model_id: str, process_description: str) -> str:
    """
    Prepare a BPMN canvas review for an existing BPMN model before generating XML.
    Use only in canvas scope when the user asks to generate, draw, update, or create a BPMN/AS-IS draft.
    Do not approve or save XML with this tool. Ask the user to approve or correct the review first.
    """
    review = workspace_database.prepare_bpmn_review(
        bpmn_model_id=bpmn_model_id,
        process_description=process_description,
    )
    return format_workspace_result("Review BPMN pronta per approvazione", review)


@tool
def prepare_process_bpmn_review(process_id: str, process_description: str) -> str:
    """
    Prepare an AS-IS/BPMN review for a process-scoped chat.
    Use in process scope when the user asks to collect, review, model, or generate an AS-IS draft.
    This resolves the process BPMN model automatically and does not save XML until approval.
    """
    process = workspace_database.get_process(process_id)
    if process is None:
        raise ValueError(f"Processo non trovato: {process_id}")

    review = workspace_database.prepare_bpmn_review(
        bpmn_model_id=process["bpmn_model_id"],
        process_description=process_description,
    )
    return format_workspace_result("Review AS-IS pronta per approvazione", review)


@tool
def approve_canvas_bpmn_review(bpmn_model_id: str) -> str:
    """
    Approve the latest BPMN canvas review and generate/save BPMN XML for the existing BPMN model.
    Use only after the user explicitly approves the prepared review.
    """
    result = workspace_database.approve_bpmn_review(bpmn_model_id=bpmn_model_id)
    safe_result = {
        "bpmn_model": {
            "id": result["bpmn_model"]["id"],
            "process_id": result["bpmn_model"]["process_id"],
            "name": result["bpmn_model"]["name"],
            "xml_saved": bool(result["bpmn_model"].get("xml")),
        },
        "review": result["review"],
    }
    return format_workspace_result("BPMN generato e salvato", safe_result)


bpmn_review_tools = [
    manage_canvas_bpmn_model,
    manage_canvas_construction,
    manage_canvas_validation,
    read_process_bpmn_xml,
    read_canvas_bpmn_xml,
    list_canvas_bpmn_elements,
    update_canvas_bpmn_element,
    add_canvas_bpmn_element,
    delete_canvas_bpmn_element,
    connect_canvas_bpmn_elements,
    reconnect_canvas_bpmn_flow,
    validate_canvas_bpmn,
    preview_canvas_bpmn_change,
    layout_canvas_bpmn,
    replace_canvas_bpmn_xml,
    list_canvas_bpmn_versions,
    restore_canvas_bpmn_version,
    prepare_process_bpmn_review,
    prepare_canvas_bpmn_review,
    approve_canvas_bpmn_review,
]
