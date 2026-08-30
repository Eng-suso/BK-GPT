from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from backend.schemas.simulation import CreateSimulationRunRequest, SimulationRunResponse
from backend.schemas.workspace import BpmnModelResponse
from backend.security import get_current_tenant_id, require_principal
from backend.simulation.service import execute_simulation_run, prepare_simulation_run
from backend.simulation.storage import get_simulation_run, list_simulation_runs
from backend.workspace_database import get_bpmn_model


router = APIRouter(
    prefix="/v1/workspace",
    tags=["simulation"],
    dependencies=[Depends(require_principal)],
)


@router.post("/bpmn-models/{bpmn_model_id}/simulation-runs")
async def create_workspace_simulation_run(
    bpmn_model_id: str,
    request: CreateSimulationRunRequest,
    background_tasks: BackgroundTasks,
) -> SimulationRunResponse:
    model = get_bpmn_model(bpmn_model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="Modello BPMN non trovato.")

    try:
        run, scenario, bpmn_xml = prepare_simulation_run(
            bpmn_model=BpmnModelResponse(**model),
            request=request,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # scenario is None when an identical run is already in flight (idempotency).
    if scenario is not None:
        background_tasks.add_task(
            execute_simulation_run,
            run_id=run["id"],
            tenant_id=get_current_tenant_id(),
            bpmn_xml=bpmn_xml,
            scenario=scenario,
            request=request,
        )

    return SimulationRunResponse(**run)


@router.get("/bpmn-models/{bpmn_model_id}/simulation-runs")
def get_workspace_simulation_runs(bpmn_model_id: str) -> list[SimulationRunResponse]:
    if get_bpmn_model(bpmn_model_id) is None:
        raise HTTPException(status_code=404, detail="Modello BPMN non trovato.")

    return [SimulationRunResponse(**run) for run in list_simulation_runs(bpmn_model_id)]


@router.get("/simulation-runs/{run_id}")
def get_workspace_simulation_run(run_id: int) -> SimulationRunResponse:
    run = get_simulation_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Simulazione non trovata.")

    return SimulationRunResponse(**run)
