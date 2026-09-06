from backend import workspace_database


def load_project_context(state: dict) -> dict:
    """
    Build a normalized context dictionary for the project identified in the input state.
    
    Args:
        state (dict): Untrusted state containing an optional ``project_id``.
    
    Returns:
        dict: An empty dictionary when no project ID is provided; otherwise, a
            context containing all expected project fields. Missing project data
            is represented by ``None`` and missing collection data by empty lists.
    
    Notes:
        This function performs read-only database lookups and does not persist
        changes. The returned context preserves a consistent set of project and
        collection keys when a project ID is supplied.
    """
    project_id = state.get("project_id")
    if not project_id:
        return {}

    project = workspace_database.get_project(project_id)
    if project is None:
        return {
            "project_name": None,
            "client_id": None,
            "client_name": None,
            "engagement_objective": None,
            "project_phase": None,
            "project_status": None,
            "progress": None,
            "next_step": None,
            "project_processes": [],
            "project_sources": [],
            "project_decisions": [],
            "project_deliverables": [],
            "project_open_issues": [],
        }

    return {
        "project_name": project["name"],
        "client_id": project["client_id"],
        "client_name": project["client"],
        # L'incarico, non solo il contenitore: senza questo la Project Chat sa
        # come si chiama il progetto e non perche' esiste (PROJECT-01).
        "engagement_objective": project.get("objective") or None,
        "project_phase": project["phase"],
        "project_status": project["status"],
        "progress": project["progress"],
        "next_step": project["next_step"],
        "project_processes": project.get("process_items") or [],
        "project_sources": workspace_database.list_project_sources(project_id),
        "project_decisions": workspace_database.list_project_decisions(project_id),
        "project_deliverables": project.get("deliverables") or [],
        "project_open_issues": project.get("open_issues") or [],
    }
