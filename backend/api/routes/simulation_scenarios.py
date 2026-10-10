"""SIM-14: il workspace degli scenari AS-IS | A | B | C di un processo."""

from fastapi import APIRouter, Depends, HTTPException

from backend.schemas.simulation_scenarios import (
    CreateScenarioRequest,
    PutScenarioBaselineRequest,
    SimulationScenarioWorkspaceResponse,
    UpdateScenarioRequest,
)
from backend.security import require_principal
from backend.simulation.scenarios import (
    ScenarioNotFound,
    ScenarioRevisionConflict,
    create_scenario,
    delete_scenario,
    get_scenario_workspace,
    put_scenario_baseline,
    update_scenario,
)
from backend.workspace_database import get_bpmn_model

router = APIRouter(
    prefix="/v1/workspace",
    tags=["simulation"],
    dependencies=[Depends(require_principal)],
)


def _require_model(bpmn_model_id: str) -> None:
    if get_bpmn_model(bpmn_model_id) is None:
        raise HTTPException(status_code=404, detail="Modello BPMN non trovato.")


@router.get("/bpmn-models/{bpmn_model_id}/simulation-scenarios")
def get_workspace_simulation_scenarios(bpmn_model_id: str) -> SimulationScenarioWorkspaceResponse:
    _require_model(bpmn_model_id)
    return get_scenario_workspace(bpmn_model_id)


@router.put("/bpmn-models/{bpmn_model_id}/simulation-scenarios/baseline")
def put_workspace_simulation_baseline(
    bpmn_model_id: str,
    request: PutScenarioBaselineRequest,
) -> SimulationScenarioWorkspaceResponse:
    _require_model(bpmn_model_id)
    try:
        return put_scenario_baseline(bpmn_model_id, request)
    except ScenarioRevisionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/bpmn-models/{bpmn_model_id}/simulation-scenarios")
def create_workspace_simulation_scenario(
    bpmn_model_id: str,
    request: CreateScenarioRequest,
) -> SimulationScenarioWorkspaceResponse:
    _require_model(bpmn_model_id)
    try:
        return create_scenario(bpmn_model_id, request)
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
    _require_model(bpmn_model_id)
    try:
        return update_scenario(bpmn_model_id, scenario_id, request)
    except ScenarioNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ScenarioRevisionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/bpmn-models/{bpmn_model_id}/simulation-scenarios/{scenario_id}")
def delete_workspace_simulation_scenario(bpmn_model_id: str, scenario_id: int) -> SimulationScenarioWorkspaceResponse:
    _require_model(bpmn_model_id)
    try:
        return delete_scenario(bpmn_model_id, scenario_id)
    except ScenarioNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
