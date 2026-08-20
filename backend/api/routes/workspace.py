from fastapi import APIRouter, HTTPException

from backend.schemas.workspace import (
    ApproveBpmnReviewResponse,
    BpmnModelResponse,
    BpmnReviewResponse,
    BpmnVersionResponse,
    ClientResponse,
    CreateClientRequest,
    CreateProcessRequest,
    CreateProjectDecisionRequest,
    CreateProjectRequest,
    CreateProjectSourceRequest,
    ProjectDecisionResponse,
    ProjectProcessResponse,
    ProjectResponse,
    ProjectSourceResponse,
    RestoreBpmnVersionResponse,
    UpdateBpmnModelRequest,
)
from backend.workspace_database import (
    approve_bpmn_review,
    create_client,
    create_process,
    create_project,
    create_project_decision,
    create_project_source,
    get_bpmn_model,
    get_bpmn_review,
    get_process,
    get_project,
    list_bpmn_versions,
    list_clients,
    list_project_decisions,
    list_project_processes,
    list_project_sources,
    list_projects,
    reset_workspace,
    restore_bpmn_version,
    update_bpmn_model,
)


router = APIRouter(prefix="/v1/workspace", tags=["workspace"])


@router.get("/clients")
def get_workspace_clients() -> list[ClientResponse]:
    return [ClientResponse(**client) for client in list_clients()]


@router.post("/clients")
def create_workspace_client(request: CreateClientRequest) -> ClientResponse:
    try:
        return ClientResponse(**create_client(**request.model_dump()))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/projects")
def get_workspace_projects() -> list[ProjectResponse]:
    return [ProjectResponse(**project) for project in list_projects()]


@router.post("/projects")
def create_workspace_project(request: CreateProjectRequest) -> ProjectResponse:
    try:
        return ProjectResponse(**create_project(**request.model_dump()))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/projects/{project_id}")
def get_workspace_project(project_id: str) -> ProjectResponse:
    project = get_project(project_id)

    if project is None:
        raise HTTPException(status_code=404, detail="Progetto non trovato.")

    return ProjectResponse(**project)


@router.get("/projects/{project_id}/processes")
def get_workspace_project_processes(project_id: str) -> list[ProjectProcessResponse]:
    return [ProjectProcessResponse(**process) for process in list_project_processes(project_id)]


@router.post("/projects/{project_id}/processes")
def create_workspace_process(
    project_id: str,
    request: CreateProcessRequest,
) -> ProjectProcessResponse:
    try:
        return ProjectProcessResponse(**create_process(project_id=project_id, **request.model_dump()))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/projects/{project_id}/sources")
def get_workspace_project_sources(project_id: str) -> list[ProjectSourceResponse]:
    return [ProjectSourceResponse(**source) for source in list_project_sources(project_id)]


@router.post("/projects/{project_id}/sources")
def create_workspace_project_source(
    project_id: str,
    request: CreateProjectSourceRequest,
) -> ProjectSourceResponse:
    try:
        return ProjectSourceResponse(**create_project_source(project_id=project_id, **request.model_dump()))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/projects/{project_id}/decisions")
def get_workspace_project_decisions(project_id: str) -> list[ProjectDecisionResponse]:
    return [ProjectDecisionResponse(**decision) for decision in list_project_decisions(project_id)]


@router.post("/projects/{project_id}/decisions")
def create_workspace_project_decision(
    project_id: str,
    request: CreateProjectDecisionRequest,
) -> ProjectDecisionResponse:
    try:
        return ProjectDecisionResponse(**create_project_decision(project_id=project_id, **request.model_dump()))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/processes/{process_id}")
def get_workspace_process(process_id: str) -> ProjectProcessResponse:
    process = get_process(process_id)

    if process is None:
        raise HTTPException(status_code=404, detail="Processo non trovato.")

    return ProjectProcessResponse(**process)


@router.get("/bpmn-models/{bpmn_model_id}")
def get_workspace_bpmn_model(bpmn_model_id: str) -> BpmnModelResponse:
    model = get_bpmn_model(bpmn_model_id)

    if model is None:
        raise HTTPException(status_code=404, detail="Modello BPMN non trovato.")

    return BpmnModelResponse(**model)


@router.put("/bpmn-models/{bpmn_model_id}")
def update_workspace_bpmn_model(
    bpmn_model_id: str,
    request: UpdateBpmnModelRequest,
) -> BpmnModelResponse:
    try:
        model = update_bpmn_model(bpmn_model_id, request.xml)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if model is None:
        raise HTTPException(status_code=404, detail="Modello BPMN non trovato.")

    return BpmnModelResponse(**model)


@router.get("/bpmn-models/{bpmn_model_id}/versions")
def get_workspace_bpmn_versions(bpmn_model_id: str) -> list[BpmnVersionResponse]:
    return [BpmnVersionResponse(**version) for version in list_bpmn_versions(bpmn_model_id)]


@router.post("/bpmn-models/{bpmn_model_id}/versions/{version_id}/restore")
def restore_workspace_bpmn_version(
    bpmn_model_id: str,
    version_id: int,
) -> RestoreBpmnVersionResponse:
    try:
        result = restore_bpmn_version(bpmn_model_id=bpmn_model_id, version_id=version_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return RestoreBpmnVersionResponse(**result)


@router.get("/bpmn-models/{bpmn_model_id}/review")
def get_workspace_bpmn_review(bpmn_model_id: str) -> BpmnReviewResponse | None:
    review = get_bpmn_review(bpmn_model_id)

    if review is None:
        return None

    return BpmnReviewResponse(**review)


@router.post("/bpmn-models/{bpmn_model_id}/review/approve")
def approve_workspace_bpmn_review(bpmn_model_id: str) -> ApproveBpmnReviewResponse:
    try:
        result = approve_bpmn_review(bpmn_model_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ApproveBpmnReviewResponse(**result)


@router.delete("")
def clear_workspace():
    reset_workspace()
    return {"status": "ok"}
