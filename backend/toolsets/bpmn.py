from typing_extensions import Annotated
from typing import Literal

from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from backend import workspace_database
from backend.bpmn import BPMNSemanticModel, semantic_model_to_bpmn_xml
from backend.graphs.routing_contracts import minimum_readiness_score, uncovered_missing_information
from backend.toolsets.common import format_workspace_result
from backend.toolsets.workspace import tool_state_write
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
    """Generate BPMN XML and metadata from the semantic model in the current context.
    
    Args:
        bpmn_model_id (str): Untrusted BPMN model identifier used to resolve review
            and semantic-model context.
        state (dict): Runtime state containing review and semantic-model context.
    
    Returns:
        tuple[str, dict]: Generated BPMN XML and metadata describing the semantic
            model, review status, element counts, and model warnings.
    
    Raises:
        ValueError: If the model context or canonical semantic model is unavailable.
    
    The function does not persist changes or modify runtime state.
    """
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


def _canvas_facade_result(
    tool_call_id: str,
    payload: dict,
    *,
    updated_xml: str | None = None,
) -> Command:
    """Publishes a canvas facade result and, when provided, the updated BPMN XML.
    
    Args:
        tool_call_id: Identifier used to associate the state update with the tool call.
        payload: Result payload to format as workspace content. Treat as untrusted input.
        updated_xml: Optional updated BPMN XML to persist in state and publish as the
            effective canvas XML. Treat as untrusted input.
    
    Returns:
        A state-writing command containing the formatted canvas result.
    
    Side Effects:
        When `updated_xml` is provided, persists it in state as the saved and effective
        BPMN XML and records a completed canvas-edit task log. Otherwise, leaves state
        unchanged.
    """
    state: dict = {}
    if updated_xml is not None:
        state = {
            "saved_bpmn_xml": updated_xml,
            "effective_bpmn_xml": updated_xml,
            "effective_bpmn_xml_source": "canvas_facade_edit",
            "current_bpmn_xml": None,
            "canvas_task_log": [
                {
                    "step": f"patch:{payload.get('operation')}",
                    "status": "completed",
                    "owner": "canvas_patch_edit_agent",
                    "summary": payload.get("change") or payload.get("operation") or "",
                }
            ],
        }

    return tool_state_write(
        tool_call_id=tool_call_id,
        state=state,
        content=format_workspace_result("Canvas BPMN gestito", payload),
    )


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
    *,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> Command:
    """
    Manage, inspect, validate, modify, and version a BPMN canvas.
    
    The operation must be supported by the canvas facade. Editing, layout, clearing,
    replacement, and version restoration persist changes to the BPMN model and
    record the resulting operation in state. Structural replacement requires
    explicit confirmation; preview operations do not persist XML.
    
    Args:
        bpmn_model_id: Untrusted BPMN model identifier.
        operation: Untrusted canvas operation to perform.
        state: Injected runtime state used to resolve current XML and store results.
        element_id: Untrusted BPMN element identifier used by element operations.
        element_type: Untrusted BPMN element type for additions.
        name: Untrusted element or flow name.
        documentation: Untrusted BPMN element documentation.
        source_id: Untrusted source element identifier for sequence-flow operations.
        target_id: Untrusted target element identifier for sequence-flow operations.
        flow_id: Untrusted sequence-flow identifier.
        proposed_xml: Untrusted BPMN XML used for preview or replacement.
        version_id: Untrusted saved-version identifier to restore.
        change_summary: Untrusted description recorded with a structural change.
        confirm_structural_change: Confirms an approved structural XML replacement.
        tool_call_id: Injected identifier used to associate the result with the
            originating tool call.
    
    Returns:
        A state-writing command containing the formatted operation result.
    
    Raises:
        ValueError: If the operation is unsupported, required input is missing,
            the BPMN model or XML cannot be found, the requested BPMN operation
            fails, or structural replacement lacks confirmation.
    """
    if operation == "inspect":
        model = workspace_database.get_bpmn_model(bpmn_model_id)
        if model is None:
            raise ValueError(f"Modello BPMN non trovato: {bpmn_model_id}")
        xml, source = _state_or_saved_canvas_xml(bpmn_model_id, state)
        return _canvas_facade_result(
            tool_call_id,
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
        return _canvas_facade_result(
            tool_call_id,
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
        return _canvas_facade_result(
            tool_call_id,
            {
                "operation": operation,
                "bpmn_model_id": bpmn_model_id,
                "source": source,
                "change": change,
                "xml_saved": True,
            },
            updated_xml=updated_xml,
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
        return _canvas_facade_result(
            tool_call_id,
            {
                "operation": operation,
                "bpmn_model_id": bpmn_model_id,
                "source": source,
                "change": change,
                "xml_saved": True,
            },
            updated_xml=updated_xml,
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
        return _canvas_facade_result(
            tool_call_id,
            {
                "operation": operation,
                "bpmn_model_id": bpmn_model_id,
                "source": source,
                "change": change,
                "xml_saved": True,
            },
            updated_xml=updated_xml,
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
        return _canvas_facade_result(
            tool_call_id,
            {
                "operation": operation,
                "bpmn_model_id": bpmn_model_id,
                "source": source,
                "change": change,
                "validation": validate_bpmn_xml(updated_xml),
                "xml_saved": True,
            },
            updated_xml=updated_xml,
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
        return _canvas_facade_result(
            tool_call_id,
            {
                "operation": operation,
                "bpmn_model_id": bpmn_model_id,
                "source": source,
                "change": change,
                "xml_saved": True,
            },
            updated_xml=updated_xml,
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
        return _canvas_facade_result(
            tool_call_id,
            {
                "operation": operation,
                "bpmn_model_id": bpmn_model_id,
                "source": source,
                "change": change,
                "xml_saved": True,
            },
            updated_xml=updated_xml,
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
        return _canvas_facade_result(
            tool_call_id,
            {
                "operation": operation,
                "bpmn_model_id": bpmn_model_id,
                "source": source,
                "validation": validate_bpmn_xml(updated_xml),
                "layout_validation": layout_validation,
                "layout_optimization": layout_optimization,
                "xml_saved": True,
            },
            updated_xml=updated_xml,
        )

    if operation == "validate_layout":
        xml, source = _state_or_saved_canvas_xml(bpmn_model_id, state)
        return _canvas_facade_result(
            tool_call_id,
            {
                "operation": operation,
                "bpmn_model_id": bpmn_model_id,
                "source": source,
                **validate_bpmn_layout(xml),
            },
        )

    if operation == "validate":
        xml, source = _state_or_saved_canvas_xml(bpmn_model_id, state)
        return _canvas_facade_result(
            tool_call_id,
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
        return _canvas_facade_result(
            tool_call_id,
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
        return _canvas_facade_result(
            tool_call_id,
            {
                "operation": operation,
                "bpmn_model_id": bpmn_model_id,
                "change_summary": change_summary or "Sostituzione strutturale canvas",
                "xml_saved": True,
            },
            updated_xml=clean_xml,
        )

    if operation == "list_versions":
        return _canvas_facade_result(
            tool_call_id,
            {
                "operation": operation,
                "bpmn_model_id": bpmn_model_id,
                "versions": workspace_database.list_bpmn_versions(bpmn_model_id),
            },
        )

    if operation == "restore_version":
        if version_id is None:
            raise ValueError("version_id obbligatorio per restore_version.")
        return _canvas_facade_result(
            tool_call_id,
            {
                "operation": operation,
                **workspace_database.restore_bpmn_version(
                    bpmn_model_id=bpmn_model_id,
                    version_id=version_id,
                ),
            },
        )

    raise ValueError(f"Operazione canvas non supportata: {operation}")


def _construction_result(
    tool_call_id: str,
    payload: dict,
    *,
    state: dict | None = None,
    status: str = "completed",
) -> Command:
    """Record a construction operation's result and task status for the next workflow step.
    
    Args:
        tool_call_id: Identifier used to associate the state update with the tool call.
        payload: Untrusted construction result containing an ``operation`` key and
            optional ``objective`` summary.
        state: Existing state values to preserve in the resulting state update.
        status: Task status recorded for the construction operation.
    
    Returns:
        A command containing the reader-facing result and state update.
    
    The payload must include ``operation``. The command persists the supplied state
    values and records a construction task-log entry; it does not modify the
    database directly.
    """
    return tool_state_write(
        tool_call_id=tool_call_id,
        state={
            **(state or {}),
            "canvas_task_log": [
                {
                    "step": f"construction:{payload['operation']}",
                    "status": status,
                    "owner": "canvas_construction_agent",
                    "summary": payload.get("objective") or "",
                }
            ],
        },
        content=format_workspace_result("Costruzione canvas BPMN", payload),
    )


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
    *,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> Command:
    """
    Constructs, previews, validates, compares, or applies significant BPMN canvas changes.
    
    The operation requires semantic process context for construction workflows. Applying a
    preview requires explicit confirmation and succeeds only when validation reports no
    blocking issues. Construction results, previews, validation data, and task metadata
    are persisted in state; approved applications also persist the cleaned BPMN XML to
    the database.
    
    Args:
        bpmn_model_id (str): Untrusted BPMN model identifier.
        operation (CanvasConstructionOperation): Untrusted construction operation to
            perform.
        state (dict): Injected runtime state used for semantic context and persisted
            workflow data.
        objective (str): Untrusted objective describing the intended construction work.
        process_id (str | None): Untrusted process identifier associated with the model.
        constraints (list[str] | None): Untrusted construction constraints.
        proposed_xml (str | None): Untrusted BPMN XML to validate, compare, or apply.
        change_summary (str | None): Untrusted description recorded when applying XML.
        confirm_apply (bool): Explicit approval required to apply a preview.
        tool_call_id (str): Injected tool-call identifier used when updating state.
    
    Returns:
        Command: A state update containing the construction result and task status.
    
    Raises:
        ValueError: If the operation is unsupported, required semantic context or
            preview XML is missing, application is not confirmed, validation reports
            blocking issues, or the BPMN model cannot be found.
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
        return _construction_result(
            tool_call_id,
            payload,
            state={"construction_plan": payload},
            status="completed" if semantic_model else "needs_context",
        )

    if operation == "generate_preview":
        xml, context = _semantic_model_to_xml_from_context(bpmn_model_id, state)
        xml, clean_report = clean_bpmn_visual_metadata_artifacts(xml)
        validation = validate_bpmn_xml(xml)
        payload = {
            "operation": operation,
            "bpmn_model_id": bpmn_model_id,
            "objective": objective,
            # The XML itself stays in state, not in the transcript: apply reads it
            # back from there. Echoing a whole BPMN document through the model to
            # hand it back one call later is how apply_approved_preview kept
            # failing with "proposed_xml obbligatorio" - and it burned thousands
            # of tokens per preview to do it.
            "preview_ready": True,
            "preview_size_chars": len(xml),
            "validation": validation,
            "context": context,
            "clean_report": clean_report,
            "constraints": constraints,
        }
        payload["business_report"] = construction_business_report(payload)
        return _construction_result(
            tool_call_id,
            payload,
            state={
                "canvas_preview_xml": xml,
                "canvas_last_validation": validation,
            },
            status="completed" if validation.get("valid") else "needs_fix",
        )

    if operation == "validate_preview":
        xml = proposed_xml or state.get("canvas_preview_xml")
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
        return _construction_result(
            tool_call_id,
            payload,
            state={
                "canvas_last_validation": validation,
                "canvas_warnings": validation.get("warnings") or [],
            },
            status="completed" if not (validation.get("issues") or []) else "needs_fix",
        )

    if operation == "compare_with_current":
        xml = proposed_xml or state.get("canvas_preview_xml")
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
        return _construction_result(tool_call_id, payload, state={"preview_diff": payload})

    if operation == "apply_approved_preview":
        # The agent decides *whether* to apply; carrying the document is the
        # runtime's job. It only has to pass proposed_xml when applying something
        # other than the preview it just generated.
        approved_xml = proposed_xml or state.get("canvas_preview_xml")
        if not approved_xml:
            raise ValueError(
                "Nessuna anteprima da applicare: esegui prima generate_preview, "
                "oppure passa proposed_xml esplicitamente."
            )
        if not confirm_apply:
            raise ValueError("apply_approved_preview richiede confirm_apply=True dopo preview e approvazione.")
        proposed_xml, clean_report = clean_bpmn_visual_metadata_artifacts(approved_xml)
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
        return _construction_result(
            tool_call_id,
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
            state={
                "saved_bpmn_xml": clean_xml,
                "effective_bpmn_xml": clean_xml,
                "effective_bpmn_xml_source": "canvas_construction_apply",
                "canvas_last_validation": validation,
                # Spent: a later apply must not silently re-apply a stale preview.
                "canvas_preview_xml": None,
            },
        )

    raise ValueError(f"Operazione construction non supportata: {operation}")


@tool
def manage_canvas_validation(
    bpmn_model_id: str,
    operation: CanvasValidationOperation,
    state: Annotated[dict, InjectedState()],
    objective: str,
    *,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> Command:
    """
    Run technical, semantic, readiness, or traceability validation for a BPMN canvas.
    
    Args:
        bpmn_model_id: [Untrusted input] Identifier of the BPMN model to validate.
        operation: [Untrusted input] Validation operation to perform.
        state: Runtime state containing canvas and review context.
        objective: [Untrusted input] Purpose of the validation request.
        tool_call_id: Injected identifier for the tool call.
    
    Returns:
        A command containing the validation result and state updates.
    
    Raises:
        ValueError: If the model or canvas XML is unavailable, required semantic
            context is missing, or the requested operation is unsupported.
    
    Side effects:
        Persists the validation report, result, warnings, next actions, and task
        status in runtime state.
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
        minimum = minimum_readiness_score(state)
        gap_state = {"process_gaps": state.get("process_gaps"), "missing_information": missing_information}
        blocking_gaps = [
            gap
            for gap in state.get("process_gaps") or []
            if isinstance(gap, dict) and str(gap.get("severity") or "").strip().casefold() == "blocking"
        ]
        # Same identity-based rule as the routing gate: a non-blocking gap
        # excuses only the open item it names, never the whole list.
        uncovered = uncovered_missing_information(gap_state)
        meets_bar = bool(readiness_score and readiness_score >= minimum)
        result = {
            "valid": meets_bar and not blocking_gaps and not uncovered,
            "readiness_score": readiness_score,
            "minimum_readiness_score": minimum,
            "missing_information": missing_information or [],
            "uncovered_missing_information": uncovered,
            "blocking_gaps": blocking_gaps,
            "warnings": [] if meets_bar else [f"Readiness sotto la soglia richiesta ({minimum}/10)."],
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

    issues = result.get("issues") or []
    warnings = result.get("warnings") or []
    report = {
        "objective": objective,
        "operation": operation,
        "xml_valid": bool(result.get("technical", {}).get("valid", result.get("valid"))),
        "semantic_valid": result.get("semantic_valid", result.get("valid")),
        "issues": issues,
        "warnings": warnings,
        "next_actions": issues,
    }
    return tool_state_write(
        tool_call_id=tool_call_id,
        # The completion loop and the scope prompt both read the last validation;
        # before this they only ever saw the one the runtime ran itself, never the
        # one the validation subagent had just produced.
        state={
            "validation_report": report,
            "canvas_last_validation": result,
            "canvas_warnings": warnings,
            "canvas_next_actions": [
                {"owner": "canvas_validation_agent", "action": "resolve_validation_issue", "issue": issue}
                for issue in issues
            ],
            "canvas_task_log": [
                {
                    "step": "validation",
                    "status": "completed" if not issues else "needs_fix",
                    "owner": "canvas_validation_agent",
                    "summary": objective,
                    "issues": issues,
                }
            ],
        },
        content=format_workspace_result(
            "Validazione canvas BPMN",
            {
                "operation": operation,
                "bpmn_model_id": bpmn_model_id,
                "source": source,
                "objective": objective,
                "result": result,
                "business_report": canvas_business_report(result),
            },
        ),
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
    *,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> Command:
    """
    Preview a proposed BPMN XML change without saving it to the model.
    
    Args:
        bpmn_model_id (str): Untrusted BPMN model identifier.
        proposed_xml (str): Untrusted proposed BPMN XML to clean and compare.
        state (dict): Injected runtime state containing the current canvas context.
        tool_call_id (str): Injected identifier used when writing the preview result.
    
    Returns:
        Command: A state-update command containing the preview diff and formatted result.
    
    Raises:
        ValueError: If the BPMN model or current XML cannot be found, or if the
            proposed XML cannot be processed.
        Exception: If BPMN comparison or state-update processing fails.
    
    The preview diff is written to runtime state for subsequent approval or review.
    The proposed XML is not persisted to the BPMN model.
    """
    current_xml, source = _state_or_saved_canvas_xml(bpmn_model_id, state)
    clean_proposed_xml = replace_bpmn_xml(proposed_xml)
    diff = {
        "bpmn_model_id": bpmn_model_id,
        "source": source,
        **preview_bpmn_xml_change(current_xml, clean_proposed_xml),
    }
    return tool_state_write(
        tool_call_id=tool_call_id,
        # A preview the next node cannot see is a preview nobody can act on.
        state={"preview_diff": diff},
        content=format_workspace_result("Anteprima modifica BPMN", diff),
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
def approve_canvas_bpmn_review(bpmn_model_id: str, override_quality_gate: bool = False) -> str:
    """
    Approve the latest BPMN canvas review and generate/save BPMN XML for the existing BPMN model.
    Use only after the user explicitly approves the prepared review. Approval is
    blocked when the quality evaluator did not return ready_to_generate or the
    compiled model has a control-flow soundness error; set
    override_quality_gate=True only when the user explicitly accepts those risks.
    """
    result = workspace_database.approve_bpmn_review(
        bpmn_model_id=bpmn_model_id, override=override_quality_gate
    )
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
