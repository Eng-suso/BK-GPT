from langchain_core.tools import tool
from pydantic import BaseModel, Field

from backend.memory.episodic import episodic_store
from backend.memory.models import (
    ConsultantSemanticMemory,
    ConsultingContextRetrievalRequest,
    ConsultingGraphRetrievalRequest,
    EpisodeMemory,
)
from backend.memory.semantic import semantic_store
from backend.toolsets.workspace import enterprise_tool_result, get_workspace_overview


class RememberConsultantFactInput(BaseModel):
    content: str = Field(description="One durable consultant-level fact, preference, rule, or stable pattern.")
    category: str = Field(description="Stable category, such as positioning, delivery_method, sales_method, or preference.")
    entity_names: list[str] = Field(default_factory=list, description="Named entities for Mem0 Graph Memory linking.")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="Confidence this should affect future turns.")
    source: str = Field(default="chat", description="Where this memory came from.")
    durability: str = Field(default="stable", description="stable, preference, profile, method, or working_assumption.")


class SaveEpisodeInput(BaseModel):
    episode_type: str = Field(description="Event type: call, note, decision, experiment, feedback, or interview.")
    title: str = Field(description="Short source-backed event title.")
    raw_content: str = Field(description="Original notes/transcript/source text. Stored as local raw source custody.")
    summary: str = Field(default="", description="Concise extracted summary.")
    insights: list[str] = Field(default_factory=list, description="Source-backed insights extracted from raw content.")
    participants: list[str] = Field(default_factory=list, description="People or roles involved.")
    project: str | None = Field(default=None, description="Related project name or id.")
    tags: list[str] = Field(default_factory=list, description="Retrieval tags.")
    occurred_at: str | None = Field(default=None, description="ISO date/time if known.")


class ManageConsultingEvidenceInput(BaseModel):
    operation: str = Field(
        description=(
            "Evidence lifecycle operation. Use list/search/inspect to retrieve source-backed evidence; "
            "use save_interview or save_episode to store new raw evidence; use update_metadata for labels; "
            "use archive for normal removal from active retrieval; use restore to reactivate; use delete only "
            "after the user explicitly confirms destructive deletion."
        )
    )
    episode_id: str | None = Field(default=None, description="Target episode_id for inspect, update_metadata, archive, restore, or delete.")
    source_id: str | None = Field(default=None, description="Optional source_id for inspect when episode_id is unknown.")
    query: str = Field(default="", description="Search/list query. Leave empty to list recent evidence.")
    episode_type: str | None = Field(default=None, description="Filter or save type: interview, call, note, decision, workshop, feedback, observation.")
    title: str = Field(default="", description="Evidence title for save/update.")
    raw_content: str = Field(default="", description="Original notes/transcript/source text for save operations.")
    summary: str = Field(default="", description="Concise extracted summary for save/update.")
    insights: list[str] = Field(default_factory=list, description="Source-backed insights for save/update.")
    participants: list[str] = Field(default_factory=list, description="People, roles or teams involved.")
    project: str | None = Field(default=None, description="Optional project name/id for consulting-level evidence.")
    tags: list[str] = Field(default_factory=list, description="Retrieval tags for save/update.")
    occurred_at: str | None = Field(default=None, description="ISO date/time if known.")
    status: str = Field(default="active", description="For list: active, archived, or any.")
    reason: str = Field(default="", description="Why this lifecycle action is being taken, especially archive/delete.")
    limit: int = Field(default=10, ge=1, le=50, description="Maximum evidence records to return.")
    include_source_text: bool = Field(default=False, description="For inspect: include raw source text when needed.")
    confirm_destructive_action: bool = Field(default=False, description="Required for hard delete. Prefer archive for ordinary removal.")
    delete_raw_source: bool = Field(default=False, description="Also delete local raw source file during confirmed hard delete.")


@tool(args_schema=RememberConsultantFactInput)
def remember_consultant_fact(
    content: str,
    category: str,
    entity_names: list[str] | None = None,
    confidence: float = 0.8,
    source: str = "chat",
    durability: str = "stable",
) -> str:
    """
    Save a durable semantic memory about the consultant.
    Use when the user shares stable information that should affect future answers:
    identity, positioning, target clients, offers, sales method, delivery method,
    communication style, preferences, recurring constraints, or DeliR usage preferences.
    Do not use for raw transcripts, dated events, temporary details, or external facts.
    Include entity_names to improve Mem0 Graph Memory/entity linking.
    Returns a confirmation message, or a clear disabled/error message if Mem0 is unavailable.
    """
    allowed_durability = {"stable", "preference", "profile", "method", "working_assumption"}
    memory = ConsultantSemanticMemory(
        category=category,
        statement=content,
        entity_names=entity_names or [],
        confidence=confidence,
        source=source,
        durability=durability if durability in allowed_durability else "stable",
    )
    return semantic_store.save_structured_consultant_memory(memory)


@tool
def search_consultant_memory(query: str, category: str | None = None) -> str:
    """
    Search durable semantic memories about the consultant.
    Use before answering questions about the consultant's preferences, identity,
    positioning, offers, target clients, sales method, delivery method, communication
    style, recurring constraints, DeliR usage, or other stable internal context.
    Do not use for dated interviews, call transcripts, source evidence, or web facts.
    Returns formatted internal memory context with memory_ids when available, or a clear
    no-results/disabled/error message.
    """
    return semantic_store.search_consultant_memory(query=query, category=category)


@tool(args_schema=ConsultingContextRetrievalRequest)
def retrieve_consulting_context(
    query: str,
    retrieval_scope: str = "both",
    category: str | None = None,
    episode_type: str | None = None,
    project: str | None = None,
    limit: int = 5,
    reason: str = "",
) -> str:
    """
    Retrieve consultant context through one structured facade.
    Use this in Consulting scope before answering questions that may depend on
    stable consultant memory, past events, interviews, source-backed evidence, or both.
    Use semantic for durable profile/method/preference context.
    Use episodic or interview for dated source-backed context.
    Use both when the user asks for synthesis across stable memory and past events.
    """
    request = ConsultingContextRetrievalRequest(
        query=query,
        retrieval_scope=retrieval_scope,
        category=category,
        episode_type=episode_type,
        project=project,
        limit=limit,
        reason=reason or "Consulting context retrieval.",
    )
    sections = [
        "CONSULTING CONTEXT RETRIEVAL",
        f"reason: {request.reason}",
        f"scope: {request.retrieval_scope}",
    ]

    if request.retrieval_scope in {"semantic", "both"}:
        sections.extend(
            [
                "",
                "SEMANTIC MEMORY",
                semantic_store.search_consultant_memory(
                    query=request.query,
                    category=request.category,
                ),
            ]
        )

    if request.retrieval_scope in {"episodic", "both"}:
        sections.extend(
            [
                "",
                "EPISODIC MEMORY",
                episodic_store.search_episode_memory(
                    query=request.query,
                    episode_type=request.episode_type,
                    project=request.project,
                    limit=request.limit,
                ),
            ]
        )

    if request.retrieval_scope == "interview":
        sections.extend(
            [
                "",
                "INTERVIEW MEMORY",
                episodic_store.search_interview_memory(
                    query=request.query,
                    project=request.project,
                    limit=request.limit,
                ),
            ]
        )

    return "\n".join(sections)


@tool(args_schema=ConsultingGraphRetrievalRequest)
def retrieve_consulting_graph_context(
    query: str,
    relation_focus: str,
    reason: str,
    entities: list[str] | None = None,
    include_workspace_overview: bool = True,
    limit: int = 5,
) -> str:
    """
    Retrieve relational consulting context through Mem0 Graph Memory-style retrieval plus optional workspace grounding.

    Use this tool when the user asks a relation-heavy question or when routing/synthesis depends on relationships, for example:
    - which clients, projects, processes, sources, decisions, risks, offers, or insights are connected;
    - which evidence supports an insight or decision;
    - which projects share a recurring pain, risk, objection, or delivery pattern;
    - how Sohay's preferences, positioning, offers, ICP, or delivery method connect to current workspace work.

    Do not use this tool for simple factual lookup, simple workspace CRUD, BPMN editing, or external/current web information.
    Do not treat Mem0 as the operational source of truth: use workspace tools for authoritative clients/projects/processes.
    """
    request = ConsultingGraphRetrievalRequest(
        query=query,
        entities=entities or [],
        relation_focus=relation_focus,
        reason=reason,
        include_workspace_overview=include_workspace_overview,
        limit=limit,
    )
    entity_query = " ".join(request.entities)
    relational_query = "\n".join(
        [
            f"relation_focus: {request.relation_focus}",
            f"entities: {entity_query or 'none'}",
            f"query: {request.query}",
        ]
    )
    semantic_result = semantic_store.search_consultant_memory(
        query=relational_query,
        category=None,
    )
    episodic_result = episodic_store.search_episode_memory(
        query=entity_query or request.query,
        limit=request.limit,
    )
    workspace_result = (
        get_workspace_overview.invoke({})
        if request.include_workspace_overview
        else "Workspace overview not requested."
    )

    return "\n".join(
        [
            "CONSULTING GRAPH CONTEXT RETRIEVAL",
            "source: mem0_graph_memory_plus_workspace_grounding",
            f"reason: {request.reason}",
            f"relation_focus: {request.relation_focus}",
            f"entities: {', '.join(request.entities) or 'none'}",
            "",
            "MEM0 RELATIONAL MEMORY",
            semantic_result,
            "",
            "EPISODIC EVIDENCE LINKS",
            episodic_result,
            "",
            "WORKSPACE GROUNDING",
            workspace_result,
            "",
            "CAVEAT",
            "Use Mem0 results as relational retrieval context. Use workspace DB records as authoritative operational state.",
        ]
    )


@tool
def forget_consultant_memory(memory_id: str, delete_linked: bool = False) -> str:
    """
    Delete one specific semantic memory by its Mem0 memory_id.
    Use only when the user explicitly asks to remove a specific durable memory.
    If the user did not provide a memory_id, search memory first and ask which memory to delete.
    Do not use for ordinary corrections, edits, or forgetting a whole category.
    Returns a deletion confirmation, or a clear disabled/error message.
    """
    return semantic_store.delete_consultant_memory(memory_id=memory_id, delete_linked=delete_linked)


@tool(args_schema=ManageConsultingEvidenceInput)
def manage_consulting_evidence(
    operation: str,
    episode_id: str | None = None,
    source_id: str | None = None,
    query: str = "",
    episode_type: str | None = None,
    title: str = "",
    raw_content: str = "",
    summary: str = "",
    insights: list[str] | None = None,
    participants: list[str] | None = None,
    project: str | None = None,
    tags: list[str] | None = None,
    occurred_at: str | None = None,
    status: str = "active",
    reason: str = "",
    limit: int = 10,
    include_source_text: bool = False,
    confirm_destructive_action: bool = False,
    delete_raw_source: bool = False,
) -> str:
    """
    Manage consulting-level source-backed evidence through one lifecycle facade.
    Use this for interviews, calls, notes, decisions, workshops, observations and
    other episodic evidence. Do not use it for durable consultant profile facts,
    preferences, methods or BPMN rules; those remain semantic memory tools.
    Prefer archive over delete when the user asks to remove evidence from active use.
    Hard delete requires confirm_destructive_action=True.
    """
    normalized_operation = operation.strip().lower()
    normalized_status = status if status in {"active", "archived", "any"} else "active"

    if normalized_operation in {"list", "search"}:
        evidence = episodic_store.list_episode_memory(
            project=project,
            episode_type=episode_type,
            query=query,
            status=normalized_status,
            limit=limit,
        )
        return enterprise_tool_result(
            status="ok",
            action="manage_consulting_evidence",
            entity_type="consulting_evidence_collection",
            summary=f"Consulting evidence {normalized_operation}: {len(evidence)} record.",
            payload={
                "operation": normalized_operation,
                "query": query,
                "project": project,
                "episode_type": episode_type,
                "status": normalized_status,
                "evidence": evidence,
            },
        )

    if normalized_operation == "inspect":
        evidence = episodic_store.get_episode_memory(
            episode_id=episode_id,
            source_id=source_id,
            include_source_text=include_source_text,
        )
        return enterprise_tool_result(
            status="ok" if evidence else "not_found",
            action="manage_consulting_evidence",
            entity_type="consulting_evidence",
            entity_id=episode_id,
            summary="Consulting evidence inspected." if evidence else "Consulting evidence not found.",
            payload={"operation": normalized_operation, "evidence": evidence},
        )

    if normalized_operation in {"save_interview", "save_episode"}:
        if not raw_content.strip():
            return enterprise_tool_result(
                status="blocked",
                action="manage_consulting_evidence",
                entity_type="consulting_evidence",
                summary="Cannot save evidence without raw_content.",
                payload={"operation": normalized_operation},
            )
        save_result = episodic_store.save_episode_memory(
            episode_type="interview" if normalized_operation == "save_interview" else (episode_type or "note"),
            title=title,
            raw_content=raw_content,
            summary=summary,
            insights=insights or [],
            participants=participants or [],
            project=project,
            tags=["interview", *(tags or [])] if normalized_operation == "save_interview" else (tags or []),
            occurred_at=occurred_at,
        )
        return enterprise_tool_result(
            status="saved",
            action="manage_consulting_evidence",
            entity_type="consulting_interview" if normalized_operation == "save_interview" else "consulting_episode",
            summary=f"Consulting evidence saved: {title or 'untitled'}",
            payload={"operation": normalized_operation, "memory_result": save_result},
        )

    if normalized_operation == "update_metadata":
        result = episodic_store.update_episode_metadata(
            episode_id=episode_id or "",
            title=title if title else None,
            summary=summary if summary else None,
            insights=insights if insights else None,
            participants=participants if participants else None,
            project=project,
            tags=tags if tags else None,
            occurred_at=occurred_at,
        )
        return enterprise_tool_result(
            status=result["status"],
            action="manage_consulting_evidence",
            entity_type="consulting_evidence",
            entity_id=episode_id,
            summary=result["message"],
            payload={"operation": normalized_operation, "result": result},
        )

    if normalized_operation == "archive":
        result = episodic_store.archive_episode_memory(episode_id=episode_id or "", reason=reason)
    elif normalized_operation == "restore":
        result = episodic_store.restore_episode_memory(episode_id=episode_id or "")
    elif normalized_operation == "delete":
        result = episodic_store.delete_episode_memory(
            episode_id=episode_id or "",
            confirm_destructive_action=confirm_destructive_action,
            delete_raw_source=delete_raw_source,
        )
    else:
        result = {
            "status": "blocked",
            "message": f"Unsupported operation: {operation}.",
        }

    return enterprise_tool_result(
        status=result["status"],
        action="manage_consulting_evidence",
        entity_type="consulting_evidence",
        entity_id=episode_id,
        summary=result["message"],
        payload={"operation": normalized_operation, "result": result},
    )


class ManageConsultantPlaybookInput(BaseModel):
    operation: str = Field(
        description=(
            "list to retrieve active playbooks relevant to a task; inspect for one "
            "playbook by id; save_candidate to store a new learned method as a "
            "candidate (NOT active); promote to run the guardrail and activate a "
            "candidate; deprecate to retire an active playbook; generalize to turn a "
            "client-scoped playbook into a consultant-scoped candidate (needs project + "
            "playbook_id, INV-13 — a rewrite, not a copy); record_outcome to log how a "
            "playbook performed (outcome worked|partial|didn't_work)."
        )
    )
    playbook_id: str | None = Field(default=None, description="Target id for inspect, promote, deprecate, record_outcome, or the source for generalize.")
    outcome: str = Field(default="", description="For record_outcome: worked, partial, or didn't_work.")
    note: str = Field(default="", description="For record_outcome: short free-text on why it worked or not.")
    query: str = Field(default="", description="Task description for list ranking. Leave empty to list recent active playbooks.")
    kind: str = Field(default="playbook", description="playbook, heuristic, or checklist. For save_candidate.")
    title: str = Field(default="", description="Short playbook title. For save_candidate.")
    applies_when: str = Field(default="", description="When this method applies. For save_candidate.")
    body: str = Field(default="", description="The reusable method: when it applies, the steps, what to avoid. For save_candidate.")
    scope: str = Field(default="consultant", description="consultant for a generalized method, client for a client-specific one.")
    project: str | None = Field(default=None, description="Workspace project id/name. Required when scope is client.")
    derived_from: list[str] = Field(default_factory=list, description="episodic_memory ids this method was extracted from (provenance).")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="Initial confidence for save_candidate.")
    limit: int = Field(default=10, ge=1, le=25, description="Max playbooks for list.")


@tool(args_schema=ManageConsultantPlaybookInput)
def manage_consultant_playbook(
    operation: str,
    playbook_id: str | None = None,
    query: str = "",
    kind: str = "playbook",
    title: str = "",
    applies_when: str = "",
    body: str = "",
    scope: str = "consultant",
    project: str | None = None,
    derived_from: list[str] | None = None,
    confidence: float = 0.5,
    limit: int = 10,
    outcome: str = "",
    note: str = "",
) -> str:
    """
    Manage the consultant's learned playbooks (procedural memory, stored in Postgres).
    Use when the consultant describes a reusable way of working that should improve
    future turns: a method, a heuristic, or a checklist. Shipped repo skills are the
    source of truth for their own content and are never edited here (INV-12); this
    tool only handles methods learned while working with the consultant.
    A new playbook is saved as a candidate and is NOT used by the agent until it is
    promoted: promote runs a guardrail (PII, and for consultant scope any leftover
    client names) and activates the playbook only if it comes back clean.
    Promoting a client-scoped playbook to consultant scope is a separate
    generalization step, never a copy (INV-13).
    Returns an enterprise tool result with the playbook id and status.
    """
    from backend.memory import canonical_memory, gateway
    from backend.memory import scope as canonical_scope
    from backend.settings import settings

    normalized_operation = (operation or "").strip().lower()
    consultant_id = settings.default_consultant_id
    # generalize opera sempre su un sorgente client-scoped, a prescindere da `scope`
    use_client_scope = (scope or "").strip().lower() == "client" or normalized_operation == "generalize"
    client_id: str | None = None
    canonical_project_id: str | None = None

    if use_client_scope:
        if not project:
            return enterprise_tool_result(
                status="blocked",
                action="manage_consultant_playbook",
                entity_type="consultant_playbook",
                summary="questa operazione richiede il parametro project.",
                payload={"operation": normalized_operation},
            )
        try:
            resolved = canonical_scope.resolve(project)
            client_id, canonical_project_id = resolved.client_id, resolved.project_id
        except Exception as exc:  # noqa: BLE001
            return enterprise_tool_result(
                status="error",
                action="manage_consultant_playbook",
                entity_type="consultant_playbook",
                summary=f"scope cliente non risolto: {exc}",
                payload={"operation": normalized_operation, "project": project},
            )

    if normalized_operation in {"list", "search"}:
        result = gateway.procedural_retrieve(
            consultant_id=consultant_id,
            client_id=client_id,
            task_text=query,
            limit=max(1, min(limit, 25)),
        )
        return enterprise_tool_result(
            status=result.get("status", "ok"),
            action="manage_consultant_playbook",
            entity_type="consultant_playbook_collection",
            summary=f"Playbook attivi pertinenti: {result.get('count', 0)}.",
            payload={"operation": normalized_operation, **result},
        )

    if normalized_operation == "inspect":
        if not playbook_id:
            return enterprise_tool_result(
                status="blocked",
                action="manage_consultant_playbook",
                entity_type="consultant_playbook",
                summary="inspect richiede playbook_id.",
                payload={"operation": normalized_operation},
            )
        detail = canonical_memory.get_procedural(
            playbook_id, consultant_id=consultant_id, client_id=client_id
        )
        return enterprise_tool_result(
            status="ok" if detail else "not_found",
            action="manage_consultant_playbook",
            entity_type="consultant_playbook",
            entity_id=playbook_id,
            summary="Playbook trovato." if detail else "Playbook non trovato.",
            payload={"operation": normalized_operation, "playbook": detail},
        )

    if normalized_operation == "save_candidate":
        if not title.strip() or not body.strip():
            return enterprise_tool_result(
                status="blocked",
                action="manage_consultant_playbook",
                entity_type="consultant_playbook",
                summary="save_candidate richiede title e body.",
                payload={"operation": normalized_operation},
            )
        try:
            new_id = canonical_memory.write_procedural_candidate(
                consultant_id,
                kind=(kind or "playbook").strip().lower(),
                title=title.strip(),
                body=body.strip(),
                applies_when=applies_when.strip() or None,
                scope="client" if use_client_scope else "consultant",
                client_id=client_id,
                project_id=canonical_project_id,
                derived_from=derived_from or [],
                confidence=confidence,
                created_by="consultant",
            )
        except Exception as exc:  # noqa: BLE001
            return enterprise_tool_result(
                status="error",
                action="manage_consultant_playbook",
                entity_type="consultant_playbook",
                summary=f"Salvataggio candidate fallito: {exc}",
                payload={"operation": normalized_operation},
            )
        return enterprise_tool_result(
            status="saved",
            action="manage_consultant_playbook",
            entity_type="consultant_playbook",
            entity_id=new_id,
            summary="Playbook salvato come candidate (non attivo finche' non promosso).",
            payload={"operation": normalized_operation, "playbook_id": new_id, "status": "candidate"},
        )

    if normalized_operation == "promote":
        if not playbook_id:
            return enterprise_tool_result(
                status="blocked",
                action="manage_consultant_playbook",
                entity_type="consultant_playbook",
                summary="promote richiede playbook_id.",
                payload={"operation": normalized_operation},
            )
        result = canonical_memory.promote_procedural(
            playbook_id, consultant_id=consultant_id, client_id=client_id
        )
        status_map = {
            "promoted": "activated",
            "guardrail_flagged": "blocked",
            "not_found": "not_found",
            "already_active": "noop",
            "blocked": "blocked",
        }
        summary_map = {
            "promoted": "Playbook promosso ad active.",
            "guardrail_flagged": "Promozione bloccata dal guardrail: generalizza il corpo e riprova.",
            "not_found": "Playbook non trovato.",
            "already_active": "Playbook gia' active.",
            "blocked": "Playbook non promuovibile.",
        }
        return enterprise_tool_result(
            status=status_map.get(result["status"], result["status"]),
            action="manage_consultant_playbook",
            entity_type="consultant_playbook",
            entity_id=playbook_id,
            summary=summary_map.get(result["status"], result["status"]),
            payload={"operation": normalized_operation, **result},
        )

    if normalized_operation == "deprecate":
        if not playbook_id:
            return enterprise_tool_result(
                status="blocked",
                action="manage_consultant_playbook",
                entity_type="consultant_playbook",
                summary="deprecate richiede playbook_id.",
                payload={"operation": normalized_operation},
            )
        result = canonical_memory.deprecate_procedural(
            playbook_id, consultant_id=consultant_id, client_id=client_id
        )
        return enterprise_tool_result(
            status=result["status"],
            action="manage_consultant_playbook",
            entity_type="consultant_playbook",
            entity_id=playbook_id,
            summary="Playbook ritirato." if result["status"] == "deprecated" else "Nessuna modifica.",
            payload={"operation": normalized_operation, **result},
        )

    if normalized_operation == "record_outcome":
        if not playbook_id or not outcome.strip():
            return enterprise_tool_result(
                status="blocked",
                action="manage_consultant_playbook",
                entity_type="consultant_playbook",
                summary="record_outcome richiede playbook_id e outcome.",
                payload={"operation": normalized_operation},
            )
        result = canonical_memory.record_playbook_outcome(
            playbook_id,
            outcome,
            consultant_id=consultant_id,
            client_id=client_id,
        )
        status_map = {"recorded": "ok", "bad_outcome": "blocked", "not_found": "not_found"}
        return enterprise_tool_result(
            status=status_map.get(result["status"], result["status"]),
            action="manage_consultant_playbook",
            entity_type="consultant_playbook",
            entity_id=playbook_id,
            summary=(
                f"Esito registrato: {result.get('outcome')}, "
                f"confidence {result.get('confidence')}"
                + (", playbook auto-deprecato." if result.get("auto_deprecated") else ".")
                if result["status"] == "recorded"
                else "Esito non registrato."
            ),
            payload={"operation": normalized_operation, "note": note, **result},
        )

    if normalized_operation == "generalize":
        if not playbook_id:
            return enterprise_tool_result(
                status="blocked",
                action="manage_consultant_playbook",
                entity_type="consultant_playbook",
                summary="generalize richiede playbook_id (il playbook client-scoped sorgente).",
                payload={"operation": normalized_operation},
            )
        result = canonical_memory.generalize_procedural(
            playbook_id, consultant_id=consultant_id, client_id=client_id
        )
        status_map = {
            "generalized": "saved",
            "not_found": "not_found",
            "blocked": "blocked",
            "no_method": "empty",
        }
        summary_map = {
            "generalized": "Candidate consultant-scoped creato dalla generalizzazione. Rivedi e poi promote.",
            "not_found": "Playbook sorgente non trovato.",
            "blocked": "Il sorgente non e' client-scoped: niente da generalizzare.",
            "no_method": "Nessun metodo generalizzabile dal playbook sorgente.",
        }
        return enterprise_tool_result(
            status=status_map.get(result["status"], result["status"]),
            action="manage_consultant_playbook",
            entity_type="consultant_playbook",
            entity_id=result.get("candidate_id") or playbook_id,
            summary=summary_map.get(result["status"], result["status"]),
            payload={"operation": normalized_operation, **result},
        )

    return enterprise_tool_result(
        status="blocked",
        action="manage_consultant_playbook",
        entity_type="consultant_playbook",
        summary=f"Operazione non supportata: {operation}.",
        payload={"operation": normalized_operation},
    )


class ExtractPlaybookFromEpisodesInput(BaseModel):
    project: str = Field(
        description="Workspace project id/name. Episodes and the resulting playbook are client-scoped."
    )
    limit: int = Field(default=8, ge=2, le=12, description="How many recent episodes to feed the extractor.")


@tool(args_schema=ExtractPlaybookFromEpisodesInput)
def extract_playbook_from_episodes(project: str, limit: int = 8) -> str:
    """
    Extract a reusable method from a project's recent episodes (procedural learning, L2).
    Reads the client-scoped episodic memory, asks an LLM to synthesize one reusable
    method (when it applies, the steps, what to avoid) and stores it as a client-scoped
    procedural_memory candidate with derived_from set to those episode ids.
    The candidate is NOT active: review the text, then use manage_consultant_playbook
    operation=promote. Idempotent on the same set of episodes: a second call returns the
    existing playbook instead of creating a duplicate.
    Returns an enterprise tool result with the candidate id and the episode ids it used.
    """
    from backend.memory import canonical_memory
    from backend.memory import scope as canonical_scope
    from backend.memory.procedural import extraction
    from backend.settings import settings

    consultant_id = settings.default_consultant_id
    try:
        resolved = canonical_scope.resolve(project)
    except Exception as exc:  # noqa: BLE001
        return enterprise_tool_result(
            status="error",
            action="extract_playbook_from_episodes",
            entity_type="consultant_playbook",
            summary=f"scope cliente non risolto: {exc}",
            payload={"project": project},
        )
    client_id, canonical_project_id = resolved.client_id, resolved.project_id

    episodes = canonical_memory.list_episodes_for_learning(
        consultant_id,
        client_id=client_id,
        project_id=canonical_project_id,
        limit=max(2, min(limit, 12)),
    )
    if len(episodes) < 2:
        return enterprise_tool_result(
            status="empty",
            action="extract_playbook_from_episodes",
            entity_type="consultant_playbook",
            summary="Meno di 2 episodi disponibili: niente da estrarre.",
            payload={"project": project, "episodes": len(episodes)},
        )

    episode_ids = [e["id"] for e in episodes]
    existing = canonical_memory.procedural_candidate_for_episodes(
        consultant_id, client_id=client_id, episode_ids=episode_ids
    )
    if existing:
        return enterprise_tool_result(
            status="noop",
            action="extract_playbook_from_episodes",
            entity_type="consultant_playbook",
            entity_id=existing,
            summary="Esiste gia' un playbook derivato da questi episodi.",
            payload={"playbook_id": existing, "derived_from": episode_ids},
        )

    extracted = extraction.extract_playbook_from_episodes(episodes)
    if extracted is None:
        return enterprise_tool_result(
            status="empty",
            action="extract_playbook_from_episodes",
            entity_type="consultant_playbook",
            summary="Nessun metodo generalizzabile dagli episodi.",
            payload={"project": project, "episodes": len(episodes)},
        )

    try:
        new_id = canonical_memory.write_procedural_candidate(
            consultant_id,
            kind=extracted.kind,
            title=extracted.title,
            body=extracted.body,
            applies_when=extracted.applies_when or None,
            scope="client",
            client_id=client_id,
            project_id=canonical_project_id,
            derived_from=episode_ids,
            confidence=extracted.confidence,
            created_by="agent",
        )
    except Exception as exc:  # noqa: BLE001
        return enterprise_tool_result(
            status="error",
            action="extract_playbook_from_episodes",
            entity_type="consultant_playbook",
            summary=f"Salvataggio candidate fallito: {exc}",
            payload={"project": project},
        )

    return enterprise_tool_result(
        status="saved",
        action="extract_playbook_from_episodes",
        entity_type="consultant_playbook",
        entity_id=new_id,
        summary="Playbook candidate estratto dagli episodi (non attivo finche' non promosso).",
        payload={
            "playbook_id": new_id,
            "status": "candidate",
            "title": extracted.title,
            "derived_from": episode_ids,
        },
    )


@tool
def remember_bpmn_preference(rule: str, area: str) -> str:
    """
    Save a durable BPMN/process modeling preference for this consultant.
    Use when the user states a stable preference or rule about BPMN style, gateways,
    events, lanes, pools, handoffs, exceptions, assumptions, readiness, validation,
    evidence policy, or process-discovery method.
    Do not use for a one-off process detail or raw interview/call evidence.
    Returns a confirmation message, or a clear disabled/error message if Mem0 is unavailable.
    """
    return semantic_store.save_bpmn_preference(rule=rule, area=area)


@tool
def search_bpmn_preferences(query: str, area: str | None = None) -> str:
    """
    Search durable BPMN/process modeling preferences for this consultant.
    Use before answering questions about how the consultant prefers BPMN/process models
    to be structured, validated, scoped, evidenced, or communicated.
    Do not use for generic BPMN knowledge, current standards/news, or raw interview evidence.
    Returns formatted internal BPMN preference context, or a clear no-results/disabled/error message.
    """
    return semantic_store.search_bpmn_preferences(query=query, area=area)


@tool(args_schema=SaveEpisodeInput)
def save_episode(
    episode_type: str,
    title: str,
    raw_content: str,
    summary: str = "",
    insights: list[str] | None = None,
    participants: list[str] | None = None,
    project: str | None = None,
    tags: list[str] | None = None,
    occurred_at: str | None = None,
) -> str:
    """
    Save an episodic memory with raw source custody and Mem0 semantic indexing.
    Use for dated, source-backed events such as calls, meeting notes, decisions,
    experiments, feedback, observations, or project moments.
    Put the original notes/transcript in raw_content. Put only extracted context in
    summary and insights. Use participants, project, tags, and occurred_at for provenance.
    Do not use for stable consultant profile facts, generic preferences, or web research.
    Returns episode_id/source_id confirmation plus Mem0 indexing result.
    """
    memory = EpisodeMemory(
        episode_type=episode_type,
        title=title,
        raw_content=raw_content,
        summary=summary,
        insights=insights or [],
        participants=participants or [],
        project=project,
        tags=tags or [],
        occurred_at=occurred_at,
    )
    return episodic_store.save_structured_episode_memory(memory)


@tool
def search_episodes(
    query: str,
    episode_type: str | None = None,
    project: str | None = None,
    limit: int = 5,
) -> str:
    """
    Search episodic memories by semantic query and local source registry.
    Use when the user asks what happened in a past event, what was said in a call/note,
    where an insight came from, which source supports an observation, or what prior
    decisions/feedback/experiments exist.
    Use episode_type to narrow to call, note, decision, experiment, feedback, or interview.
    Do not use for stable consultant preferences or profile-level facts unless the user
    asks for source evidence.
    Returns Mem0 episodic results plus local registry matches with episode_id, source_id,
    date, participants, project, tags, summary, insights, and source_path when available.
    """
    return episodic_store.search_episode_memory(
        query=query,
        episode_type=episode_type,
        project=project,
        limit=limit,
    )


@tool
def save_interview(
    title: str,
    raw_content: str,
    summary: str = "",
    insights: str = "",
    participants: str = "",
    project: str | None = None,
    tags: str = "",
    occurred_at: str | None = None,
) -> str:
    """
    Save an interview as episodic memory.
    Use for customer/prospect/user/consultant interviews, discovery transcripts, or
    interview notes. Keep the transcript or original notes in raw_content; use summary
    and insights only for extracted context. Use participants, project, tags, and
    occurred_at for provenance.
    Do not use for stable preferences unless the interview insight has been confirmed
    as durable memory separately.
    Returns episode_id/source_id confirmation plus Mem0 indexing result.
    """
    return episodic_store.save_interview_memory(
        title=title,
        raw_content=raw_content,
        summary=summary,
        insights=insights,
        participants=participants,
        project=project,
        tags=tags,
        occurred_at=occurred_at,
    )


@tool
def search_interviews(
    query: str,
    project: str | None = None,
    limit: int = 5,
) -> str:
    """
    Search saved interviews.
    Use when the user asks about interview evidence, customer language, discovery findings,
    recurring pain points, objections, needs, quotes/context, or where an interview insight
    came from.
    Do not use for generic consultant preferences unless the user asks for interview-backed evidence.
    Returns Mem0 interview results plus local registry matches with episode_id, source_id,
    date, participants, project, tags, summary, insights, and source_path when available.
    """
    return episodic_store.search_interview_memory(
        query=query,
        project=project,
        limit=limit,
    )


memory_tools = [
    remember_consultant_fact,
    search_consultant_memory,
    retrieve_consulting_context,
    retrieve_consulting_graph_context,
    forget_consultant_memory,
    manage_consulting_evidence,
    manage_consultant_playbook,
    extract_playbook_from_episodes,
    remember_bpmn_preference,
    search_bpmn_preferences,
    save_episode,
    search_episodes,
    save_interview,
    search_interviews,
]
