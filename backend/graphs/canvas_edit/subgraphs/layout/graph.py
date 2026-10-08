"""Product-owned drawing workflow. LLMs never choose geometry."""
from langchain_core.runnables import RunnableConfig
from langgraph.graph import START, END, StateGraph

from backend import workspace_database
from backend.bpmn.canvas_layout import ENTERPRISE_POLICY
from backend.graphs.canvas_edit.state import CanvasState
from backend.workspace_services.bpmn_canvas_edit import optimize_bpmn_layout

LAYOUT_SUBGRAPH_CONTRACT = """
All agent canvas writes use DeliR's mandatory CanvasLayoutPolicy. Agents request
semantic changes only; no positions, dimensions, rows or routes are accepted.
Normalization, graph ranks, real-owner lanes, orthogonal routing and visual lint
run deterministically before BPMN DI is committed. Preserve semantic documents,
annotations, evidence, conditions and source/target references. Manual consultant
geometry is preserved and validated on its separate save path.
""".strip()


def _layout_xml_from_state(state: CanvasState) -> tuple[dict | None, str]:
    model_id = state.get("bpmn_model_id")
    model = workspace_database.get_bpmn_model(model_id) if model_id else None
    xml = (state.get("effective_bpmn_xml") or state.get("current_bpmn_xml") or (model or {}).get("xml") or "").strip()
    return model, xml


def build_canvas_layout_consultant_agent(llm=None):
    """Compatibility node: select the system policy without invoking an LLM."""
    def select_policy(state: CanvasState, config: RunnableConfig) -> dict:
        return {
            "canvas_layout_plan": {"policy": ENTERPRISE_POLICY.version},
            "canvas_task_log": [{"step": "layout_plan", "status": "completed",
                                 "owner": "canvas_layout_policy", "summary": "Policy di disegno DeliR selezionata."}],
        }
    return select_policy


def run_canvas_drawing_agent(state: CanvasState) -> dict:
    model_id = state.get("bpmn_model_id")
    model, xml = _layout_xml_from_state(state)
    try:
        if not model_id or not model or not xml:
            raise ValueError("Missing prerequisite: bpmn_model_id/effective_bpmn_xml")
        updated_xml, optimization = optimize_bpmn_layout(xml)
        report = optimization["selected_report"]
        if not optimization["valid"]:
            raise ValueError("; ".join(report["issues"]))
        saved = workspace_database.update_bpmn_model(
            model_id, updated_xml, change_summary="Layout BPMN aggiornato", source="canvas_layout_agent",
        )
        if saved is None:
            raise ValueError("Modello BPMN non disponibile per il salvataggio.")
    except ValueError as exc:
        return {
            "canvas_layout_status": "blocked", "canvas_loop_status": "blocked",
            "blocking_conditions": [str(exc)],
            "canvas_task_log": [{"step": "layout", "status": "blocked", "owner": "layout_subgraph", "summary": str(exc)}],
        }
    actual_xml = saved["xml"]
    return {
        "saved_bpmn_xml": actual_xml, "effective_bpmn_xml": actual_xml,
        "effective_bpmn_xml_source": "layout_subgraph", "canvas_layout_status": "completed",
        "canvas_layout_report": report, "canvas_loop_status": state.get("canvas_loop_status"),
        "blocking_conditions": state.get("blocking_conditions") or [],
        "canvas_task_log": [{"step": "layout", "status": "completed", "owner": "layout_subgraph",
                             "summary": "Canvas ridisegnato e validato secondo la policy DeliR.",
                             "report": report, "plan": {"policy": ENTERPRISE_POLICY.version}}],
    }


def build_layout_subgraph(llm=None):
    """Keep the caller API; drawing always runs independently of LLM planning."""
    workflow = StateGraph(CanvasState)
    workflow.add_node("canvas_layout_policy", build_canvas_layout_consultant_agent())
    workflow.add_node("canvas_drawing_agent", run_canvas_drawing_agent)
    workflow.add_edge(START, "canvas_layout_policy")
    workflow.add_edge("canvas_layout_policy", "canvas_drawing_agent")
    workflow.add_edge("canvas_drawing_agent", END)
    return workflow.compile()
