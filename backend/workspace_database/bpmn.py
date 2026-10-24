"""Modelli BPMN e loro versioni, con il controllo sulle scritture concorrenti.
"""

from sqlalchemy import select

from backend.agents.chat_mode import assert_write_allowed
from backend.agents.run_context import BpmnVersionConflict, active_turn_writes
from backend.workspace_database._common import now_iso, tenant_id, tenant_row
from backend.workspace_database.conformance import _queue_conformance
from backend.workspace_storage import (
    WorkspaceBpmnModel,
    WorkspaceBpmnReview,
    WorkspaceBpmnVersion,
    workspace_connection,
)


def get_bpmn_model(bpmn_model_id: str) -> dict | None:
    with workspace_connection() as session:
        model = tenant_row(session, WorkspaceBpmnModel, bpmn_model_id)

        if model is None:
            return None

        return {
            "id": model.id,
            "process_id": model.process_id,
            "name": model.name,
            "xml": model.xml,
            "version_id": _latest_bpmn_version_id(session, model.id),
        }


def _latest_bpmn_version(session, bpmn_model_id: str) -> WorkspaceBpmnVersion | None:
    statement = (
        select(WorkspaceBpmnVersion)
        .where(WorkspaceBpmnVersion.bpmn_model_id == bpmn_model_id)
        .where(WorkspaceBpmnVersion.tenant_id == tenant_id())
        .order_by(WorkspaceBpmnVersion.id.desc())
        .limit(1)
    )
    return session.execute(statement).scalars().first()


def _latest_bpmn_version_id(session, bpmn_model_id: str) -> int | None:
    latest = _latest_bpmn_version(session, bpmn_model_id)
    return latest.id if latest is not None else None


class _NoPrecondition:
    """Chi scrive non ha detto da quale versione parte (chiamanti interni)."""


NO_PRECONDITION = _NoPrecondition()


def _assert_bpmn_not_changed_underneath(
    session,
    bpmn_model_id: str,
    expected_version_id: int | None | _NoPrecondition,
) -> None:
    """Rifiuta una scrittura che cancellerebbe una versione che chi scrive non ha visto.

    Due controlli, indipendenti:
    - `expected_version_id`: chi salva a mano dice da quale versione e' partito.
      `None` vuol dire "da nessuna": il modello non aveva ancora versioni, e se
      ora ne ha una e' di qualcun altro. `NO_PRECONDITION` salta il controllo;
    - il registro del turno: dentro un agent run, una versione nata dopo
      l'inizio del turno e non scritta dal turno e' di qualcun altro.

    Va chiamata con la riga del modello gia' bloccata (`FOR UPDATE`), o due
    scritture concorrenti passerebbero entrambe il controllo.
    """
    latest = _latest_bpmn_version(session, bpmn_model_id)
    latest_id = latest.id if latest is not None else None
    if not isinstance(expected_version_id, _NoPrecondition) and latest_id != expected_version_id:
        raise BpmnVersionConflict(
            "Il diagramma e' stato salvato da un'altra parte dopo che lo hai aperto. "
            "Ricarica il canvas per vedere l'ultima versione prima di salvare."
        )

    turn = active_turn_writes()
    if turn is None or latest is None:
        return
    if bpmn_model_id in turn.base_version_by_model:
        # L'XML su cui lavora l'agente viene da una versione nota - o da
        # nessuna, il diagramma iniziale: vale quella, anche se l'altra
        # scrittura e' arrivata prima dell'inizio del turno (una scheda rimasta
        # aperta su una versione vecchia, o due canvas su un processo nuovo).
        changed = latest.id != turn.base_version_by_model[bpmn_model_id]
    else:
        changed = latest.id not in turn.written_version_ids and latest.created_at > turn.started_at
    if changed:
        raise BpmnVersionConflict(
            "Il consulente ha salvato il diagramma mentre lavoravi: la tua modifica "
            "lo sovrascriverebbe. Non e' stata salvata. Prima rileggi il canvas "
            "salvato, poi rifai la modifica su quella versione."
        )


def _remember_turn_write(bpmn_model_id: str, version_id: int) -> None:
    """La versione appena scritta dal turno diventa la sua nuova base."""
    turn = active_turn_writes()
    if turn is not None:
        turn.written_version_ids.add(version_id)
        turn.base_version_by_model[bpmn_model_id] = version_id


def bpmn_version_to_dict(version: WorkspaceBpmnVersion) -> dict:
    return {
        "id": version.id,
        "bpmn_model_id": version.bpmn_model_id,
        "process_id": version.process_id,
        "xml": version.xml,
        "change_summary": version.change_summary,
        "source": version.source,
        "created_at": version.created_at,
    }


def create_bpmn_version(
    session,
    model: WorkspaceBpmnModel,
    xml: str,
    change_summary: str,
    source: str,
) -> WorkspaceBpmnVersion:
    """Create and stage a BPMN version snapshot for a model.
    
    Args:
        session: SQLAlchemy session used to stage the new version.
        model (WorkspaceBpmnModel): Model associated with the version.
        xml (str): Untrusted BPMN XML content to store.
        change_summary (str): Untrusted description of the change; blank values use a default.
        source (str): Untrusted version source; blank values use ``"manual"``.
    
    Returns:
        WorkspaceBpmnVersion: The newly created, unsaved version entity.
    
    Raises:
        AuthorizationError: If the current user is not permitted to write BPMN data.
    
    The version inherits the model's tenant, model, and process identifiers. The entity is added to
    the session but is not committed.
    """
    assert_write_allowed("create_bpmn_version")
    xml = _canvas_xml_for_write(xml, source=source, process_name=model.name)
    version = WorkspaceBpmnVersion(
        tenant_id=getattr(model, "tenant_id", tenant_id()),
        bpmn_model_id=model.id,
        process_id=model.process_id,
        xml=xml,
        change_summary=change_summary.strip() or "Aggiornamento BPMN",
        source=source.strip() or "manual",
        created_at=now_iso(),
    )
    session.add(version)
    return version


def _canvas_xml_for_write(xml: str, *, source: str, process_name: str | None = None) -> str:
    """Runtime actor is authoritative; source also covers system drawing jobs."""
    from backend.agents.chat_mode import active_mode
    from backend.bpmn.canvas_layout import apply_enterprise_layout
    from backend.workspace_services.bpmn_canvas_edit import validate_bpmn_layout, validate_bpmn_xml
    if active_mode() is not None or source.startswith("canvas_") or source in {"review_approval", "plan_draft"}:
        return apply_enterprise_layout(xml, process_name=process_name)
    # This low-level store also serves legacy records with no diagram yet.
    # A present manual diagram is validated without changing a single byte.
    if "BPMNDiagram" in xml:
        from backend.bpmn.canvas_layout.normalizer import normalize_semantics
        normalize_semantics(xml)  # Validate semantics on a copy; preserve the original DI bytes.
        semantic = validate_bpmn_xml(xml)
        report = validate_bpmn_layout(xml)
        report["issues"].extend(semantic["issues"])
        if report["issues"]:
            raise ValueError("Disegno manuale non valido: " + "; ".join(report["issues"]))
    return xml


def update_bpmn_model(
    bpmn_model_id: str,
    xml: str,
    change_summary: str = "Salvataggio canvas",
    source: str = "manual_save",
    expected_version_id: int | None | _NoPrecondition = NO_PRECONDITION,
) -> dict | None:
    """
    Persist an authorized BPMN model update and create a version snapshot.
    
    Args:
        bpmn_model_id (str): Tenant-scoped model identifier.
        xml (str): Untrusted BPMN XML content; it must contain non-whitespace
            characters.
        change_summary (str): Untrusted description of the change.
        source (str): Untrusted origin label for the version snapshot.
        expected_version_id (int | None): Untrusted id of the version the
            writer started from; `None` means the model had no version yet.
            When given, the save is refused if the latest version differs.
            Omitted (`NO_PRECONDITION`) for internal callers.
    
    Returns:
        dict | None: The updated model data, or `None` when the model does not
        belong to the current tenant or does not exist.
    
    Raises:
        PermissionError: If the caller is not authorized to write BPMN models.
        ValueError: If `xml` is empty or contains only whitespace.
        BpmnVersionConflict: If someone else saved a version the writer has
            not seen (see `_assert_bpmn_not_changed_underneath`).
    
    Side Effects:
        Updates the tenant-owned BPMN model and persists a version snapshot.
    """
    assert_write_allowed("update_bpmn_model")
    with workspace_connection() as session:
        model = tenant_row(session, WorkspaceBpmnModel, bpmn_model_id)

        if model is None:
            return None

        clean_xml = xml.strip()
        if not clean_xml:
            raise ValueError("XML BPMN obbligatorio.")

        # Blocca la riga del modello fino al commit: due salvataggi concorrenti
        # si mettono in fila, e il secondo vede la versione scritta dal primo.
        session.refresh(model, with_for_update=True)
        _assert_bpmn_not_changed_underneath(session, model.id, expected_version_id)

        clean_xml = _canvas_xml_for_write(clean_xml, source=source, process_name=model.name)
        model.xml = clean_xml
        # Il disegno e' cambiato: il confronto con le fonti che risultava prima
        # non descrive piu' cio' che si vede. Va rifatto, e lo fa il worker.
        review = session.get(WorkspaceBpmnReview, bpmn_model_id)
        if review is not None and getattr(review, "tenant_id", "local") == tenant_id():
            _queue_conformance(review)
        version = create_bpmn_version(
            session=session,
            model=model,
            xml=clean_xml,
            change_summary=change_summary,
            source=source,
        )
        session.flush()
        _remember_turn_write(model.id, version.id)
        return {
            "id": model.id,
            "process_id": model.process_id,
            "name": model.name,
            "xml": model.xml,
            "version_id": version.id,
        }


def list_bpmn_versions(bpmn_model_id: str) -> list[dict]:
    with workspace_connection() as session:
        if tenant_row(session, WorkspaceBpmnModel, bpmn_model_id) is None:
            return []

        statement = (
            select(WorkspaceBpmnVersion)
            .where(WorkspaceBpmnVersion.bpmn_model_id == bpmn_model_id)
            .where(WorkspaceBpmnVersion.tenant_id == tenant_id())
            .order_by(WorkspaceBpmnVersion.id.desc())
        )
        versions = session.execute(statement).scalars().all()
        return [bpmn_version_to_dict(version) for version in versions]


def restore_bpmn_version(bpmn_model_id: str, version_id: int) -> dict:
    """Restore a tenant-owned BPMN model to a prior version and record the restoration.
    
    Args:
        bpmn_model_id (str): Untrusted BPMN model identifier.
        version_id (int): Untrusted version identifier to restore.
    
    Returns:
        dict: The restored BPMN model, the source version, and the newly created
            restoration version.
    
    Raises:
        ValueError: If the model or version does not exist, or the version does
            not belong to the specified model and current tenant.
        PermissionError: If the caller is not authorized to modify BPMN data.
    
    Side Effects:
        Persists the restored XML and creates a new BPMN version recording the
        restoration.
    """
    assert_write_allowed("restore_bpmn_version")
    with workspace_connection() as session:
        model = tenant_row(session, WorkspaceBpmnModel, bpmn_model_id)
        version = session.get(WorkspaceBpmnVersion, version_id)

        if model is None:
            raise ValueError(f"Modello BPMN non trovato: {bpmn_model_id}")
        if (
            version is None
            or version.bpmn_model_id != bpmn_model_id
            or getattr(version, "tenant_id", "local") != tenant_id()
        ):
            raise ValueError(f"Versione BPMN non trovata: {version_id}")

        # Come ogni scrittura del disegno: in fila dietro le altre, e mai sopra
        # una versione che chi ripristina (dentro un turno) non ha visto.
        session.refresh(model, with_for_update=True)
        _assert_bpmn_not_changed_underneath(session, model.id, NO_PRECONDITION)
        model.xml = _canvas_xml_for_write(version.xml, source="restore", process_name=model.name)
        # Il disegno ripristinato e' un disegno nuovo per il confronto con le
        # fonti: quello registrato parla della versione appena sostituita.
        review = tenant_row(session, WorkspaceBpmnReview, bpmn_model_id)
        if review is not None:
            _queue_conformance(review)
        restored = create_bpmn_version(
            session=session,
            model=model,
            xml=model.xml,
            change_summary=f"Ripristino versione {version_id}",
            source="restore",
        )
        session.flush()
        _remember_turn_write(model.id, restored.id)
        return {
            "bpmn_model": {
                "id": model.id,
                "process_id": model.process_id,
                "name": model.name,
                "xml": model.xml,
                "version_id": restored.id,
            },
            "restored_from": bpmn_version_to_dict(version),
            "created_version": bpmn_version_to_dict(restored),
        }
