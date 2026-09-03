from langgraph.graph import START, END, StateGraph

from backend import workspace_database
from backend.graphs.canvas_edit.subgraphs.layout.state import CanvasLayoutState
from backend.workspace_services.bpmn_canvas_edit import clean_bpmn_visual_metadata_artifacts, optimize_bpmn_layout


LAYOUT_SUBGRAPH_CONTRACT = """
Canvas Drawing/Layout subgraph contract.

Own only the visual arrangement of the BPMN canvas: spacing, row wrapping,
lane shape sizing and edge routing. Before layout, remove canvas-only annotation
noise: free-text annotations and the association edges that dock to them. Keep
the data perspective (data objects, data stores and their read/write
associations): it is part of the operating view and must be laid out readably,
docked to the activities that produce or consume it, without overlapping flow
nodes or lanes. Handoffs, business rules, unknowns, evidence and traceability
stay in BPMNSemanticModel/sourceProcessUnderstanding/compilationPlan, not on the
canvas. Do not change process semantics, labels, ownership, sequence flow
source/target or business meaning. A layout pass is successful only when the
drawing has no overlapping flow nodes or data artifacts, visible positions for
all shapes and a readable overall aspect ratio.
""".strip()


def run_canvas_drawing_agent(state: CanvasLayoutState) -> dict:
    bpmn_model_id = state.get("bpmn_model_id")
    if not bpmn_model_id:
        return {
            "canvas_layout_status": "blocked",
            "canvas_loop_status": "blocked",
            "blocking_conditions": ["Missing prerequisite: bpmn_model_id"],
            "canvas_task_log": [
                {
                    "step": "layout",
                    "status": "blocked",
                    "owner": "layout_subgraph",
                    "summary": "Impossibile disegnare il canvas: bpmn_model_id mancante.",
                }
            ],
        }

    model = workspace_database.get_bpmn_model(bpmn_model_id)
    xml = (state.get("effective_bpmn_xml") or state.get("current_bpmn_xml") or (model or {}).get("xml") or "").strip()
    if not model or not xml:
        return {
            "canvas_layout_status": "blocked",
            "canvas_loop_status": "blocked",
            "blocking_conditions": ["Missing prerequisite: effective_bpmn_xml"],
            "canvas_task_log": [
                {
                    "step": "layout",
                    "status": "blocked",
                    "owner": "layout_subgraph",
                    "summary": "Impossibile disegnare il canvas: XML BPMN mancante.",
                }
            ],
        }

    clean_xml, clean_report = clean_bpmn_visual_metadata_artifacts(xml)
    updated_xml, optimization = optimize_bpmn_layout(clean_xml)
    report = optimization.get("selected_report") or {}
    attempts = optimization.get("attempts") or []
    status = "completed" if optimization.get("valid") else "blocked"
    saved_model = workspace_database.update_bpmn_model(
        bpmn_model_id,
        updated_xml,
        change_summary="Layout BPMN aggiornato",
        source="canvas_layout_agent",
    )
    if saved_model is None:
        status = "blocked"

    return {
        "saved_bpmn_xml": updated_xml,
        "effective_bpmn_xml": updated_xml,
        "effective_bpmn_xml_source": "layout_subgraph",
        "canvas_layout_status": status,
        "canvas_layout_report": report,
        "canvas_loop_status": "blocked" if status == "blocked" else state.get("canvas_loop_status"),
        "blocking_conditions": (report.get("issues") or [])
        if status == "blocked"
        else (state.get("blocking_conditions") or []),
        "canvas_task_log": [
            {
                "step": "layout",
                "status": status,
                "owner": "layout_subgraph",
                "summary": "Canvas ridisegnato e validato per leggibilita'."
                if status == "completed"
                else "Il layout del canvas richiede intervento: la validazione geometrica non passa.",
                "report": report,
                "clean_report": clean_report,
            }
        ],
        "layout_steps": [
            {
                "status": status,
                "attempts": len(attempts),
                "optimization": optimization,
                "report": report,
            }
        ],
    }


def build_layout_subgraph():
    workflow = StateGraph(CanvasLayoutState)
    workflow.add_node("canvas_drawing_agent", run_canvas_drawing_agent)
    workflow.add_edge(START, "canvas_drawing_agent")
    workflow.add_edge("canvas_drawing_agent", END)
    return workflow.compile()
