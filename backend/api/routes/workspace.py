from fastapi import APIRouter, Depends, HTTPException

from backend.schemas.workspace import (
    AnswerBpmnReviewQuestionRequest,
    ApproveBpmnReviewResponse,
    ArchiveImpactResponse,
    ArchiveRequest,
    ArchiveResponse,
    BpmnModelResponse,
    BpmnReviewResponse,
    BpmnReviewVersionResponse,
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
    ReviseBpmnReviewRequest,
    UpdateBpmnModelRequest,
    UpdateBpmnReviewRequest,
    UpdateClientRequest,
    UpdateProcessRequest,
    UpdateProjectRequest,
)
from backend.security import AuthPrincipal, require_admin_principal, require_principal
from backend.workspace_database import (
    answer_bpmn_review_question,
    approve_bpmn_review,
    archive_client,
    archive_process,
    archive_project,
    client_impact,
    create_client,
    create_process,
    create_project,
    create_project_decision,
    create_project_source,
    delete_client,
    delete_process,
    delete_project,
    get_bpmn_model,
    get_bpmn_review,
    get_bpmn_review_version,
    list_bpmn_review_versions,
    get_process,
    get_project,
    list_archive,
    list_bpmn_versions,
    list_clients,
    list_project_decisions,
    list_project_processes,
    list_project_sources,
    list_projects,
    process_impact,
    project_impact,
    reset_workspace,
    restore_bpmn_version,
    restore_client,
    restore_process,
    restore_project,
    update_bpmn_model,
    revise_bpmn_review,
    update_bpmn_review_brief,
    update_client,
    update_process,
    update_project,
)


router = APIRouter(prefix="/v1/workspace", tags=["workspace"], dependencies=[Depends(require_principal)])


def _edit_error(exc: ValueError) -> HTTPException:
    """Maps database edit errors to HTTP responses.
    
    Args:
        exc (ValueError): Untrusted error input used to determine the response status
            and detail message.
    
    Returns:
        HTTPException: A 404 exception when the error indicates a missing record;
            otherwise, a 400 exception for an invalid modification.
    
    """
    missing = "non trovato" in str(exc).lower()
    return HTTPException(status_code=404 if missing else 400, detail=str(exc))


@router.get("/clients")
def get_workspace_clients(include_archived: bool = False) -> list[ClientResponse]:
    """Retrieve the workspace clients.

    Args:
        include_archived: Include closed clients. Off by default: the directory
            shows the work in progress.

    Returns:
        list[ClientResponse]: The workspace clients.
    """
    return [ClientResponse(**client) for client in list_clients(include_archived=include_archived)]


@router.post("/clients")
def create_workspace_client(request: CreateClientRequest) -> ClientResponse:
    """Create and persist a workspace client from the request data.
    
    Args:
        request (CreateClientRequest): Untrusted client data to validate and persist.
    
    Returns:
        ClientResponse: The newly created client.
    
    Raises:
        HTTPException: With status code 400 when the client data is invalid.
    """
    try:
        return ClientResponse(**create_client(**request.model_dump()))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/clients/{client_id}")
def update_workspace_client(client_id: str, request: UpdateClientRequest) -> ClientResponse:
    """
    Partially updates a workspace client's editable fields and persists the changes.
    
    Args:
        client_id (str): Untrusted client identifier.
        request (UpdateClientRequest): Untrusted update payload; omitted fields remain unchanged.
    
    Returns:
        ClientResponse: The updated client.
    
    Raises:
        HTTPException: With status 404 when the client does not exist, or 400 when the update is invalid.
    
    Side Effects:
        Persists the client update.
    """
    try:
        return ClientResponse(**update_client(client_id, **request.model_dump(exclude_unset=True)))
    except ValueError as exc:
        raise _edit_error(exc) from exc


@router.get("/projects")
def get_workspace_projects(include_archived: bool = False) -> list[ProjectResponse]:
    """List the workspace projects.

    Args:
        include_archived: Include closed projects. Off by default.

    Returns:
        list[ProjectResponse]: The workspace projects.
    """
    return [
        ProjectResponse(**project)
        for project in list_projects(include_archived=include_archived)
    ]


# ---------------------------------------------------------------------------
# Ciclo di vita dei record
#
# Tre verbi distinti, perche' sono tre decisioni distinte: archiviare chiude un
# incarico e lo lascia leggibile, ripristinare lo riapre, eliminare lo perde.
# L'endpoint di impatto esiste perche' una conferma deve dire cosa succede, e
# quel numero lo conosce solo il database.
# ---------------------------------------------------------------------------


@router.get("/archive")
def get_workspace_archive() -> ArchiveResponse:
    """Everything that has been closed: clients, projects and processes."""
    archive = list_archive()
    return ArchiveResponse(
        clients=[ClientResponse(**client) for client in archive["clients"]],
        projects=[ProjectResponse(**project) for project in archive["projects"]],
        processes=[ProjectProcessResponse(**process) for process in archive["processes"]],
    )


@router.get("/clients/{client_id}/impact")
def get_client_impact(client_id: str) -> ArchiveImpactResponse:
    """What closing or deleting this client would take with it."""
    try:
        return ArchiveImpactResponse(**client_impact(client_id))
    except ValueError as exc:
        raise _edit_error(exc) from exc


@router.post("/clients/{client_id}/archive")
def archive_workspace_client(client_id: str, request: ArchiveRequest) -> ClientResponse:
    """Close a client, and with it its projects and processes."""
    try:
        return ClientResponse(**archive_client(client_id, request.reason))
    except ValueError as exc:
        raise _edit_error(exc) from exc


@router.post("/clients/{client_id}/restore")
def restore_workspace_client(client_id: str) -> ClientResponse:
    """Reopen a client and whatever was closed together with it."""
    try:
        return ClientResponse(**restore_client(client_id))
    except ValueError as exc:
        raise _edit_error(exc) from exc


@router.delete("/clients/{client_id}")
def delete_workspace_client(
    client_id: str,
    _principal: AuthPrincipal = Depends(require_admin_principal),
) -> ArchiveImpactResponse:
    """Delete a client and everything under it. Not reversible."""
    try:
        return ArchiveImpactResponse(**delete_client(client_id))
    except ValueError as exc:
        raise _edit_error(exc) from exc


@router.get("/projects/{project_id}/impact")
def get_project_impact(project_id: str) -> ArchiveImpactResponse:
    """What closing or deleting this project would take with it."""
    try:
        return ArchiveImpactResponse(**project_impact(project_id))
    except ValueError as exc:
        raise _edit_error(exc) from exc


@router.post("/projects/{project_id}/archive")
def archive_workspace_project(project_id: str, request: ArchiveRequest) -> ProjectResponse:
    """Close a project and its processes."""
    try:
        return ProjectResponse(**archive_project(project_id, request.reason))
    except ValueError as exc:
        raise _edit_error(exc) from exc


@router.post("/projects/{project_id}/restore")
def restore_workspace_project(project_id: str) -> ProjectResponse:
    """Reopen a project, and its client when that was closed too."""
    try:
        return ProjectResponse(**restore_project(project_id))
    except ValueError as exc:
        raise _edit_error(exc) from exc


@router.delete("/projects/{project_id}")
def delete_workspace_project(
    project_id: str,
    _principal: AuthPrincipal = Depends(require_admin_principal),
) -> ArchiveImpactResponse:
    """Delete a project, its processes, sources and decisions. Not reversible."""
    try:
        return ArchiveImpactResponse(**delete_project(project_id))
    except ValueError as exc:
        raise _edit_error(exc) from exc


@router.get("/processes/{process_id}/impact")
def get_process_impact(process_id: str) -> ArchiveImpactResponse:
    """What closing or deleting this process would take with it."""
    try:
        return ArchiveImpactResponse(**process_impact(process_id))
    except ValueError as exc:
        raise _edit_error(exc) from exc


@router.post("/processes/{process_id}/archive")
def archive_workspace_process(process_id: str, request: ArchiveRequest) -> ProjectProcessResponse:
    """Close a process, leaving its project open."""
    try:
        return ProjectProcessResponse(**archive_process(process_id, request.reason))
    except ValueError as exc:
        raise _edit_error(exc) from exc


@router.post("/processes/{process_id}/restore")
def restore_workspace_process(process_id: str) -> ProjectProcessResponse:
    """Reopen a process, and its project when that was closed too."""
    try:
        return ProjectProcessResponse(**restore_process(process_id))
    except ValueError as exc:
        raise _edit_error(exc) from exc


@router.delete("/processes/{process_id}")
def delete_workspace_process(
    process_id: str,
    _principal: AuthPrincipal = Depends(require_admin_principal),
) -> ArchiveImpactResponse:
    """Delete a process, its BPMN model, versions and simulation runs. Not reversible."""
    try:
        return ArchiveImpactResponse(**delete_process(process_id))
    except ValueError as exc:
        raise _edit_error(exc) from exc


@router.post("/projects")
def create_workspace_project(request: CreateProjectRequest) -> ProjectResponse:
    try:
        return ProjectResponse(**create_project(**request.model_dump()))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/projects/{project_id}")
def get_workspace_project(project_id: str) -> ProjectResponse:
    """Retrieve a workspace project by its identifier.
    
    Args:
        project_id: Untrusted project identifier used to locate the project.
    
    Returns:
        The project response.
    
    Raises:
        HTTPException: With status code 404 when the project does not exist.
    
    This function does not modify or persist data.
    """
    project = get_project(project_id)

    if project is None:
        raise HTTPException(status_code=404, detail="Progetto non trovato.")

    return ProjectResponse(**project)


@router.patch("/projects/{project_id}")
def update_workspace_project(project_id: str, request: UpdateProjectRequest) -> ProjectResponse:
    """Partially update a workspace project and persist the changes.
    
    Args:
        project_id: Untrusted project identifier.
        request: Untrusted update payload containing fields to modify. Unset fields
            remain unchanged.
    
    Returns:
        The updated project.
    
    Raises:
        HTTPException: With status 404 when the project does not exist, or 400
            when the requested update is invalid.
    
    Side effects:
        Persists the project changes.
    """
    try:
        return ProjectResponse(**update_project(project_id, **request.model_dump(exclude_unset=True)))
    except ValueError as exc:
        raise _edit_error(exc) from exc


@router.get("/projects/{project_id}/processes")
def get_workspace_project_processes(project_id: str) -> list[ProjectProcessResponse]:
    """List the processes associated with a project.
    
    Args:
        project_id: Untrusted identifier of the project whose processes are requested.
    
    Returns:
        The project's processes as response models.
    """
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
    """Create a decision for a project and persist it.
    
    Args:
        project_id (str): Untrusted project identifier.
        request (CreateProjectDecisionRequest): Untrusted decision data.
    
    Returns:
        ProjectDecisionResponse: The newly created project decision.
    
    Raises:
        HTTPException: With status code 400 when the decision data is invalid.
    """
    try:
        return ProjectDecisionResponse(**create_project_decision(project_id=project_id, **request.model_dump()))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/processes/{process_id}")
def update_workspace_process(process_id: str, request: UpdateProcessRequest) -> ProjectProcessResponse:
    """
    Update editable fields of a workspace process and persist the changes.
    
    Args:
        process_id (str): Untrusted process identifier.
        request (UpdateProcessRequest): Untrusted partial update containing editable process fields.
    
    Returns:
        ProjectProcessResponse: The updated process.
    
    Raises:
        HTTPException: A 404 response if the process is not found, or a 400 response if the update is invalid.
    """
    try:
        return ProjectProcessResponse(
            **update_process(process_id, **request.model_dump(exclude_unset=True))
        )
    except ValueError as exc:
        raise _edit_error(exc) from exc


@router.get("/processes/{process_id}")
def get_workspace_process(process_id: str) -> ProjectProcessResponse:
    """Retrieve a workspace process by ID.
    
    Args:
        process_id: Untrusted process identifier used to locate the process.
    
    Returns:
        The process represented as a `ProjectProcessResponse`.
    
    Raises:
        HTTPException: With status code 404 if the process does not exist.
    """
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


@router.put("/bpmn-models/{bpmn_model_id}/review")
def update_workspace_bpmn_review(
    bpmn_model_id: str,
    payload: UpdateBpmnReviewRequest,
) -> BpmnReviewResponse:
    """Update the BPMN review brief for a model.
    
    Args:
        bpmn_model_id: Untrusted model identifier.
        payload: Untrusted request containing the replacement review brief.
    
    Returns:
        The updated BPMN review.
    
    Raises:
        HTTPException: With status 400 when the review update is invalid.
    
    The update is persisted before the response is returned.
    """
    try:
        review = update_bpmn_review_brief(bpmn_model_id, payload.bpmn_brief)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return BpmnReviewResponse(**review)


@router.get("/bpmn-models/{bpmn_model_id}/review/versions")
def list_workspace_bpmn_review_versions(
    bpmn_model_id: str,
) -> list[BpmnReviewVersionResponse]:
    """List stored review versions for a BPMN model.
    
    Args:
        bpmn_model_id: Untrusted identifier of the BPMN model.
    
    Returns:
        A list of BPMN review version responses. The function performs a
        read-only lookup and does not modify persisted data.
    """
    return [
        BpmnReviewVersionResponse(**version)
        for version in list_bpmn_review_versions(bpmn_model_id)
    ]


@router.get("/bpmn-models/{bpmn_model_id}/review/versions/{version}")
def get_workspace_bpmn_review_version(
    bpmn_model_id: str,
    version: int,
) -> BpmnReviewVersionResponse:
    """
    Retrieve a specific BPMN review version.
    
    Args:
        bpmn_model_id (str): Untrusted BPMN model identifier.
        version (int): Untrusted review version number.
    
    Returns:
        BpmnReviewVersionResponse: The requested review version.
    
    Raises:
        HTTPException: With status 404 when the review version does not exist.
    
    This function performs no persistence or other side effects.
    """
    stored = get_bpmn_review_version(bpmn_model_id, version)
    if stored is None:
        raise HTTPException(status_code=404, detail="Versione review non trovata.")

    return BpmnReviewVersionResponse(**stored)


@router.post("/bpmn-models/{bpmn_model_id}/review/answers")
def answer_workspace_bpmn_review_question(
    bpmn_model_id: str,
    payload: AnswerBpmnReviewQuestionRequest,
) -> BpmnReviewResponse:
    """Record an answer to a question in a BPMN model review.
    
    Args:
        bpmn_model_id (str): Untrusted BPMN model identifier.
        payload (AnswerBpmnReviewQuestionRequest): Untrusted question and answer data.
    
    Returns:
        BpmnReviewResponse: The updated review.
    
    Raises:
        HTTPException: With status code 400 when the answer cannot be recorded.
    
    The operation persists the submitted answer and returns the resulting review.
    """
    try:
        review = answer_bpmn_review_question(
            bpmn_model_id,
            question=payload.question,
            answer=payload.answer,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return BpmnReviewResponse(**review)


@router.post("/bpmn-models/{bpmn_model_id}/review/revise")
def revise_workspace_bpmn_review(
    bpmn_model_id: str,
    payload: ReviseBpmnReviewRequest,
) -> BpmnReviewResponse:
    """Revise the BPMN review's process understanding and change summary.
    
    Args:
        bpmn_model_id (str): Untrusted BPMN model identifier.
        payload (ReviseBpmnReviewRequest): Untrusted revision data to persist.
    
    Returns:
        BpmnReviewResponse: The updated BPMN review.
    
    Raises:
        HTTPException: With status code 400 when the revision is invalid.
    
    Side Effects:
        Persists the revised review data.
    """
    try:
        review = revise_bpmn_review(
            bpmn_model_id,
            process_understanding=payload.process_understanding,
            change_summary=payload.change_summary,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return BpmnReviewResponse(**review)


@router.post("/bpmn-models/{bpmn_model_id}/review/approve")
def approve_workspace_bpmn_review(
    bpmn_model_id: str,
    override: bool = False,
) -> ApproveBpmnReviewResponse:
    """Approve a BPMN review and persist its approved state.
    
    Args:
        bpmn_model_id (str): Untrusted BPMN model identifier.
        override (bool): Whether to allow approval despite review constraints.
    
    Returns:
        ApproveBpmnReviewResponse: The approved review details.
    
    Raises:
        HTTPException: With status code 400 when the review cannot be approved.
    """
    try:
        result = approve_bpmn_review(bpmn_model_id, override=override)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ApproveBpmnReviewResponse(**result)


@router.delete("")
def clear_workspace(_principal: AuthPrincipal = Depends(require_admin_principal)):
    reset_workspace()
    return {"status": "ok"}
