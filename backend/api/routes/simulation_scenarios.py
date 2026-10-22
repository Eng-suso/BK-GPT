"""SIM-14: il workspace degli scenari AS-IS | A | B | C di un processo."""

from fastapi import APIRouter, Depends, HTTPException

from backend.schemas.simulation_scenarios import (
    CreateScenarioRequest,
    PutScenarioBaselineRequest,
    PutScenarioOutcomeRequest,
    SimulationScenarioWorkspaceResponse,
    UpdateScenarioRequest,
)
from backend.security import require_principal
from backend.simulation.scenarios import (
    ScenarioNotFound,
    ScenarioRevisionConflict,
    bpmn_fingerprint,
    create_scenario,
    delete_scenario,
    get_scenario_workspace,
    put_scenario_baseline,
    set_scenario_outcome,
    update_scenario,
)
from backend.simulation.outcomes import build_outcome
from backend.workspace_database import get_bpmn_model

router = APIRouter(
    prefix="/v1/workspace",
    tags=["simulation"],
    dependencies=[Depends(require_principal)],
)


def _require_model(bpmn_model_id: str) -> dict:
    model = get_bpmn_model(bpmn_model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="Modello BPMN non trovato.")
    return model


def _with_fingerprint(workspace: SimulationScenarioWorkspaceResponse, model: dict) -> SimulationScenarioWorkspaceResponse:
    return workspace.model_copy(update={"bpmn_fingerprint": bpmn_fingerprint(model.get("xml"))})


@router.get("/bpmn-models/{bpmn_model_id}/simulation-scenarios")
def get_workspace_simulation_scenarios(bpmn_model_id: str) -> SimulationScenarioWorkspaceResponse:
    model = _require_model(bpmn_model_id)
    return _with_fingerprint(get_scenario_workspace(bpmn_model_id), model)


@router.put("/bpmn-models/{bpmn_model_id}/simulation-scenarios/baseline")
def put_workspace_simulation_baseline(
    bpmn_model_id: str,
    request: PutScenarioBaselineRequest,
) -> SimulationScenarioWorkspaceResponse:
    model = _require_model(bpmn_model_id)
    try:
        return _with_fingerprint(put_scenario_baseline(bpmn_model_id, request), model)
    except ScenarioRevisionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/bpmn-models/{bpmn_model_id}/simulation-scenarios")
def create_workspace_simulation_scenario(
    bpmn_model_id: str,
    request: CreateScenarioRequest,
) -> SimulationScenarioWorkspaceResponse:
    model = _require_model(bpmn_model_id)
    try:
        return _with_fingerprint(create_scenario(bpmn_model_id, request), model)
    except ScenarioRevisionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/bpmn-models/{bpmn_model_id}/simulation-scenarios/{scenario_id}")
def update_workspace_simulation_scenario(
    bpmn_model_id: str,
    scenario_id: int,
    request: UpdateScenarioRequest,
) -> SimulationScenarioWorkspaceResponse:
    model = _require_model(bpmn_model_id)
    try:
        return _with_fingerprint(update_scenario(bpmn_model_id, scenario_id, request), model)
    except ScenarioNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ScenarioRevisionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/bpmn-models/{bpmn_model_id}/simulation-scenarios/{scenario_id}")
def delete_workspace_simulation_scenario(bpmn_model_id: str, scenario_id: int) -> SimulationScenarioWorkspaceResponse:
    model = _require_model(bpmn_model_id)
    try:
        return _with_fingerprint(delete_scenario(bpmn_model_id, scenario_id), model)
    except ScenarioNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/bpmn-models/{bpmn_model_id}/simulation-scenarios/{scenario_id}/outcome")
def put_workspace_simulation_outcome(
    bpmn_model_id: str,
    scenario_id: int,
    request: PutScenarioOutcomeRequest,
) -> SimulationScenarioWorkspaceResponse:
    """SIM-28: l'alternativa e' stata implementata; misura il prima e il dopo dal log reale."""
    model = _require_model(bpmn_model_id)
    try:
        outcome = build_outcome(model["process_id"], request)
        return _with_fingerprint(set_scenario_outcome(bpmn_model_id, scenario_id, outcome), model)
    except ScenarioNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/bpmn-models/{bpmn_model_id}/simulation-scenarios/{scenario_id}/outcome")
def delete_workspace_simulation_outcome(bpmn_model_id: str, scenario_id: int) -> SimulationScenarioWorkspaceResponse:
    model = _require_model(bpmn_model_id)
    try:
        return _with_fingerprint(set_scenario_outcome(bpmn_model_id, scenario_id, None), model)
    except ScenarioNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
