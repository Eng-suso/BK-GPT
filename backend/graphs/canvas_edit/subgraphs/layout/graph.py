import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import START, END, StateGraph
from pydantic import BaseModel, ConfigDict, Field

from backend import workspace_database
from backend.graphs.canvas_edit.subgraphs.layout.state import CanvasLayoutState
from backend.llm_streaming import stream_to_text
from backend.workspace_services.bpmn_canvas_edit import (
    BpmnLayoutConfig,
    clean_bpmn_visual_metadata_artifacts,
    list_bpmn_elements,
    optimize_bpmn_layout,
    validate_bpmn_layout,
)


LAYOUT_SUBGRAPH_CONTRACT = """
Canvas Drawing/Layout subgraph contract.

Own only the visual arrangement of the BPMN canvas through an explicit
consultant layout plan: objective, task split, readable rows, then drawing. The
drawing agent must not invent a hidden fallback layout when the consultant plan
is missing or incomplete. Before layout, remove canvas-only annotation noise:
free-text annotations and the association edges that dock to them. Keep the data
perspective (data objects, data stores and their read/write associations): it is
part of the operating view and must be laid out readably, docked to the
activities that produce or consume it, without overlapping flow nodes or lanes.
Handoffs, business rules, unknowns, evidence and traceability stay in
BPMNSemanticModel/sourceProcessUnderstanding/compilationPlan, not on the canvas.
Do not change process semantics, labels, ownership, sequence flow source/target
or business meaning. A layout pass is successful only when BPMN flow nodes and
data artifacts do not overlap, every shape has a visible position and the
overall aspect ratio is readable. Sequence flows, message flows and labels are
connectors or text, not overlapping elements.
""".strip()


class CanvasLayoutPlan(BaseModel):
    model_config = ConfigDict(extra="ignore")

    strategy: str = "consultant_paper"
    tasks: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    max_nodes_per_row: int = Field(default=5, ge=3, le=6)
    column_gap: int = Field(default=320, ge=260, le=390)
    row_gap: int = Field(default=210, ge=180, le=280)
    lane_row_height: int = Field(default=210, ge=180, le=280)
    annotation_columns: int = Field(default=3, ge=2, le=5)
    rationale: str = ""


LAYOUT_CONSULTANT_PROMPT = """
You are the BPMN canvas layout consultant for DeliR.
Decide a readable drawing strategy like a senior process consultant sketching on
paper, while respecting BPMN semantics. Return only JSON matching:
{"strategy": "...", "tasks": ["..."], "rows": [["Start", "Task_A", "End"]],
"max_nodes_per_row": 3-6, "column_gap": 260-390,
"row_gap": 180-280, "lane_row_height": 180-280, "annotation_columns": 2-5,
"rationale": "..."}

Principles:
- start events belong visually on the left;
- end events should finish to the right of their row;
- the main path reads left to right;
- branches and retries may sit on lower rows;
- put BPMN ids in rows, not labels;
- include every visible BPMN flow node exactly once;
- do not put sequence flows, message flows or labels in rows;
- split the goal into concrete layout tasks before choosing rows;
- keep the drawing readable without forcing a tiny zoom;
- prefer fewer than six visible columns for dense enterprise canvases.
""".strip()


def _layout_xml_from_state(state: CanvasLayoutState) -> tuple[dict | None, str]:
    bpmn_model_id = state.get("bpmn_model_id")
    model = workspace_database.get_bpmn_model(bpmn_model_id) if bpmn_model_id else None
    xml = (state.get("effective_bpmn_xml") or state.get("current_bpmn_xml") or (model or {}).get("xml") or "").strip()
    return model, xml


def _extract_json_object(content: str) -> dict[str, Any]:
    start = content.find("{")
    end = content.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        parsed = json.loads(content[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _plan_to_config(plan: dict | CanvasLayoutPlan | None) -> BpmnLayoutConfig | None:
    if not plan:
        return None
    try:
        parsed = plan if isinstance(plan, CanvasLayoutPlan) else CanvasLayoutPlan.model_validate(plan)
    except Exception:
        return None
    return BpmnLayoutConfig(
        max_nodes_per_row=parsed.max_nodes_per_row,
        column_gap=parsed.column_gap,
        row_gap=parsed.row_gap,
        lane_row_height=parsed.lane_row_height,
        annotation_columns=parsed.annotation_columns,
    )


def _planned_rows_from_plan(plan: dict | None) -> list[list[str]] | None:
    if not plan:
        return None
    rows = plan.get("rows")
    if not isinstance(rows, list):
        return None
    planned_rows = []
    for row in rows:
        if not isinstance(row, list):
            continue
        ids = [item for item in row if isinstance(item, str) and item.strip()]
        if ids:
            planned_rows.append(ids)
    return planned_rows or None


def build_canvas_layout_consultant_agent(llm):
    def plan_canvas_layout(state: CanvasLayoutState, config: RunnableConfig) -> dict:
        _model, xml = _layout_xml_from_state(state)
        if not xml:
            return {"canvas_layout_plan": None}

        clean_xml, _clean_report = clean_bpmn_visual_metadata_artifacts(xml)
        layout_report = validate_bpmn_layout(clean_xml)
        elements = list_bpmn_elements(clean_xml)
        visible_elements = [
            {
                "type": item.get("type"),
                "name": item.get("name"),
                "id": item.get("id"),
            }
            for item in elements
            if item.get("type")
            in {
                "startEvent",
                "endEvent",
                "task",
                "userTask",
                "serviceTask",
                "manualTask",
                "exclusiveGateway",
                "parallelGateway",
                "inclusiveGateway",
                "eventBasedGateway",
                "lane",
            }
        ][:40]
        prompt = {
            "objective": state.get("canvas_objective") or state.get("goal") or "Rendere il canvas leggibile",
            "current_layout": layout_report,
            "visible_elements": visible_elements,
            "constraints": {
                "max_readable_width": 1900,
                "left_to_right": True,
                "start_left": True,
                "end_right": True,
                "avoid_tiny_zoom": True,
            },
        }
        raw_plan = stream_to_text(
            llm,
            [
                SystemMessage(content=LAYOUT_CONSULTANT_PROMPT),
                HumanMessage(content=json.dumps(prompt, ensure_ascii=True)),
            ],
            config=config,
        )
        plan = CanvasLayoutPlan.model_validate(_extract_json_object(raw_plan)).model_dump(mode="json")
        if not plan["tasks"]:
            plan["tasks"] = [
                "identifica percorso principale",
                "separa rami e ritorni",
                "posiziona start a sinistra",
                "mantieni end a destra",
                "verifica leggibilita",
            ]
        if not plan["rows"]:
            return {
                "canvas_layout_plan": plan,
                "canvas_layout_status": "blocked",
                "canvas_loop_status": "blocked",
                "blocking_conditions": ["Il layout consultant non ha prodotto righe di disegno esplicite."],
                "canvas_task_log": [
                    {
                        "step": "layout_plan",
                        "status": "blocked",
                        "owner": "canvas_layout_consultant_agent",
                        "summary": "Il piano layout non contiene righe esplicite da applicare.",
                        "plan": plan,
                    }
                ],
            }
        return {
            "canvas_layout_plan": plan,
            "canvas_task_log": [
                {
                    "step": "layout_plan",
                    "status": "completed",
                    "owner": "canvas_layout_consultant_agent",
                    "summary": "Piano layout consulenziale preparato.",
                    "plan": plan,
                }
            ],
        }

    return plan_canvas_layout


def run_canvas_drawing_agent(state: CanvasLayoutState) -> dict:
    if state.get("canvas_layout_status") == "blocked":
        return {
            "canvas_layout_status": "blocked",
            "canvas_loop_status": "blocked",
            "blocking_conditions": state.get("blocking_conditions") or [],
            "canvas_task_log": [
                {
                    "step": "layout",
                    "status": "blocked",
                    "owner": "canvas_drawing_agent",
                    "summary": "Disegno non eseguito per piano layout incompleto.",
                }
            ],
        }

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

    model, xml = _layout_xml_from_state(state)
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
    layout_plan = state.get("canvas_layout_plan")
    layout_config = _plan_to_config(layout_plan)
    planned_rows = _planned_rows_from_plan(layout_plan)
    if layout_config is None or planned_rows is None:
        return {
            "canvas_layout_status": "blocked",
            "canvas_loop_status": "blocked",
            "blocking_conditions": ["Missing prerequisite: canvas_layout_plan"],
            "canvas_task_log": [
                {
                    "step": "layout",
                    "status": "blocked",
                    "owner": "canvas_drawing_agent",
                    "summary": "Disegno non eseguito: manca un piano layout esplicito del consultant agent.",
                }
            ],
            "layout_steps": [
                {
                    "status": "blocked",
                    "attempts": 0,
                    "plan": layout_plan,
                    "clean_report": clean_report,
                }
            ],
        }
    try:
        updated_xml, optimization = optimize_bpmn_layout(
            clean_xml,
            config=layout_config,
            planned_rows=planned_rows,
            require_planned_rows=True,
        )
    except ValueError as exc:
        return {
            "canvas_layout_status": "blocked",
            "canvas_loop_status": "blocked",
            "blocking_conditions": [str(exc)],
            "canvas_task_log": [
                {
                    "step": "layout",
                    "status": "blocked",
                    "owner": "canvas_drawing_agent",
                    "summary": "Disegno non eseguito: il piano layout non e' applicabile.",
                    "plan": layout_plan,
                    "clean_report": clean_report,
                }
            ],
            "layout_steps": [
                {
                    "status": "blocked",
                    "attempts": 0,
                    "plan": layout_plan,
                    "clean_report": clean_report,
                }
            ],
        }
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
                "plan": layout_plan,
            }
        ],
        "layout_steps": [
            {
                "status": status,
                "attempts": len(attempts),
                "optimization": optimization,
                "report": report,
                "plan": state.get("canvas_layout_plan"),
            }
        ],
    }


def build_layout_subgraph(llm=None):
    workflow = StateGraph(CanvasLayoutState)
    if llm is not None:
        workflow.add_node("canvas_layout_consultant_agent", build_canvas_layout_consultant_agent(llm))
    workflow.add_node("canvas_drawing_agent", run_canvas_drawing_agent)
    if llm is not None:
        workflow.add_edge(START, "canvas_layout_consultant_agent")
        workflow.add_edge("canvas_layout_consultant_agent", "canvas_drawing_agent")
    else:
        workflow.add_edge(START, "canvas_drawing_agent")
    workflow.add_edge("canvas_drawing_agent", END)
    return workflow.compile()
