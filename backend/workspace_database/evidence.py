"""Dall'evidenza al grafo: affermazioni estratte, riconciliazione, divergenze e
proiezione, ognuna con la sua coda.
"""

import json
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import and_, delete, or_, select

from backend.workspace_database._common import now_iso, tenant_id, tenant_row
from backend.workspace_storage import (
    WorkspaceClaimRelation,
    WorkspaceEvidenceSegment,
    WorkspaceSource,
    WorkspaceSourceClaim,
    workspace_connection,
)


if TYPE_CHECKING:
    from backend.workspace_services.evidence.claims import ClaimsResult
    from backend.workspace_services.evidence.reconcile import ReconcileResult


#: Quanti altri file entrano al massimo nel confronto di una fonte (P1.13). Il
#: prompt ha gia' il suo tetto in caratteri (`reconcile.MAX_INPUT_CHARS`), ma una
#: fonte del cliente si confronta con tutti i file del cliente: senza un tetto
#: anche sulla lettura, un cliente grande li tirerebbe su tutti a ogni passata.
MAX_RECONCILE_CANDIDATES = 200


CLAIMS_MAX_ATTEMPTS = 3


CLAIMS_BACKOFF_SECONDS = 60


# Un'estrazione lunga dura quanto il modello: il lease la copre intera.
CLAIMS_LEASE_SECONDS = 900


def due_source_claims(limit: int = 1, *, only_tenant_id: str | None = None) -> list[dict]:
    """Prende in carico le fonti di cui estrarre le affermazioni.

    Come la lettura: il tentativo si conta alla presa in carico, cosi' una
    estrazione che fa cadere il worker non torna in coda per sempre.
    """
    now = now_iso()
    lease_until = (datetime.now(UTC) + timedelta(seconds=CLAIMS_LEASE_SECONDS)).isoformat(timespec="seconds")
    with workspace_connection() as session:
        statement = (
            select(WorkspaceSource)
            .where(WorkspaceSource.claims_status == "pending")
            .where(WorkspaceSource.claims_next_attempt_at <= now)
            .order_by(WorkspaceSource.claims_next_attempt_at)
            .limit(max(1, int(limit)))
            .with_for_update(skip_locked=True)
        )
        if only_tenant_id:
            statement = statement.where(WorkspaceSource.tenant_id == only_tenant_id)
        claimed = []
        for row in session.execute(statement).scalars().all():
            if row.claims_attempts >= CLAIMS_MAX_ATTEMPTS:
                row.claims_status = "failed"
                row.claims_next_attempt_at = None
                row.claims_error = row.claims_error or "L'estrazione si e' interrotta troppe volte."
                continue
            row.claims_attempts += 1
            row.claims_next_attempt_at = lease_until
            claimed.append(
                {
                    "id": row.id,
                    "tenant_id": row.tenant_id,
                    "name": row.name,
                    "project_id": row.project_id,
                    "process_id": row.process_id,
                    "content_hash": row.content_hash,
                }
            )
        session.flush()
        return claimed


def complete_source_claims(source_id: str, result: "ClaimsResult", *, content_hash: str) -> int | None:
    """Scrive le affermazioni estratte, al posto di quelle di prima.

    `result` e' un `ClaimsResult` di `evidence.claims`.

    Returns:
        Quante affermazioni sono state scritte, o `None` se la fonte non c'e'.
    """
    with workspace_connection() as session:
        source = tenant_row(session, WorkspaceSource, source_id)
        if source is None:
            return None
        session.execute(delete(WorkspaceSourceClaim).where(WorkspaceSourceClaim.source_id == source_id))
        now = now_iso()
        session.add_all(
            WorkspaceSourceClaim(
                tenant_id=source.tenant_id,
                source_id=source_id,
                ordinal=ordinal,
                statement=claim.statement,
                segment_ordinal=claim.segment_ordinal,
                anchor_ref=claim.anchor_ref,
                quote=claim.quote.replace("\x00", ""),
                quote_verified=claim.quote_verified,
                content_hash=content_hash,
                prompt_version=result.prompt_version,
                extracted_at=now,
            )
            for ordinal, claim in enumerate(result.claims)
        )
        source.claims_status = "done"
        source.claims_next_attempt_at = None
        # P1.13: prima di andare nel grafo, le affermazioni nuove si
        # confrontano con quelle degli altri file del processo.
        source.reconcile_status = "pending"
        source.reconcile_attempts = 0
        source.reconcile_error = None
        source.reconcile_next_attempt_at = now
        # Fatto, ma non tutto: lo si dice invece di farlo credere completo.
        source.claims_error = (
            f"Lette le prime porzioni: {result.segments_left_out} rimaste fuori per la lunghezza."
            if result.segments_left_out
            else None
        )
        session.flush()
        return len(result.claims)


def fail_source_claims(source_id: str, *, error: str, permanent: bool) -> None:
    """Un'estrazione non riuscita: si riprova con backoff, ma non per sempre."""
    with workspace_connection() as session:
        source = tenant_row(session, WorkspaceSource, source_id)
        if source is None:
            return
        source.claims_error = str(error)[:2000]
        if permanent or source.claims_attempts >= CLAIMS_MAX_ATTEMPTS:
            source.claims_status = "failed"
            source.claims_next_attempt_at = None
        else:
            delay = CLAIMS_BACKOFF_SECONDS * (2 ** max(0, source.claims_attempts - 1))
            source.claims_next_attempt_at = (datetime.now(UTC) + timedelta(seconds=delay)).isoformat(
                timespec="seconds"
            )
        session.flush()


RECONCILE_MAX_ATTEMPTS = 3


RECONCILE_BACKOFF_SECONDS = 60


RECONCILE_LEASE_SECONDS = 900


def _queue_graph(source: WorkspaceSource) -> None:
    """La fonte entra nella coda del grafo (P1.14), che sostituisce cio' che c'era."""
    source.graph_status = "pending"
    source.graph_attempts = 0
    source.graph_error = None
    source.graph_next_attempt_at = now_iso()


def due_source_reconcile(limit: int = 1, *, only_tenant_id: str | None = None) -> list[dict]:
    """Prende in carico le fonti da confrontare con gli altri file del processo.

    Il tentativo si conta alla presa in carico, come nelle altre code.
    """
    now = now_iso()
    lease_until = (datetime.now(UTC) + timedelta(seconds=RECONCILE_LEASE_SECONDS)).isoformat(timespec="seconds")
    with workspace_connection() as session:
        statement = (
            select(WorkspaceSource)
            .where(WorkspaceSource.reconcile_status == "pending")
            .where(WorkspaceSource.reconcile_next_attempt_at <= now)
            .order_by(WorkspaceSource.reconcile_next_attempt_at)
            .limit(max(1, int(limit)))
            .with_for_update(skip_locked=True)
        )
        if only_tenant_id:
            statement = statement.where(WorkspaceSource.tenant_id == only_tenant_id)
        claimed = []
        for row in session.execute(statement).scalars().all():
            if row.reconcile_attempts >= RECONCILE_MAX_ATTEMPTS:
                row.reconcile_status = "failed"
                row.reconcile_next_attempt_at = None
                row.reconcile_error = row.reconcile_error or "Il confronto si e' interrotto troppe volte."
                # Il grafo non aspetta un confronto che non arrivera'.
                _queue_graph(row)
                continue
            row.reconcile_attempts += 1
            row.reconcile_next_attempt_at = lease_until
            claimed.append(
                {
                    "id": row.id,
                    "tenant_id": row.tenant_id,
                    "project_id": row.project_id,
                    "process_id": row.process_id,
                }
            )
        session.flush()
        return claimed


def _claims_as_input(session, sources: list) -> list[dict]:
    # Righe ORM o tuple (`id`, `name`): servono solo quei due campi.
    names = {source.id: source.name for source in sources}
    if not names:
        return []
    rows = session.execute(
        select(WorkspaceSourceClaim)
        .where(WorkspaceSourceClaim.source_id.in_(list(names)))
        .order_by(WorkspaceSourceClaim.source_id, WorkspaceSourceClaim.ordinal)
    ).scalars().all()
    return [
        {"id": row.id, "statement": row.statement, "source_id": row.source_id, "source_name": names[row.source_id]}
        for row in rows
    ]


def reconcile_inputs(source_id: str) -> tuple[list[dict], list[dict]]:
    """Le affermazioni della fonte e quelle degli altri file con cui confrontarle.

    Gli altri file sono quelli confermati, gia' estratti, dello stesso progetto e
    dello stesso processo. Un file a livello di progetto (senza processo) si
    confronta con tutti i file del progetto, e tutti con lui. Le fonti del cliente
    (P1.16) valgono per tutti i suoi progetti: entrano nel confronto di ogni file
    del cliente, e una fonte del cliente si confronta con tutti.

    Returns:
        `(nuove, gia' presenti)`, entrambe con `id`, `statement`, `source_id`,
        `source_name`.
    """
    with workspace_connection() as session:
        source = tenant_row(session, WorkspaceSource, source_id)
        if source is None:
            return [], []
        client_wide = and_(WorkspaceSource.project_id.is_(None), WorkspaceSource.client_id == source.client_id)
        # Solo id e nome: la riga intera porta con se' il testo estratto.
        # In ordine di id, lo stesso in cui le affermazioni arrivano al prompt.
        others = (
            select(WorkspaceSource.id, WorkspaceSource.name)
            .where(WorkspaceSource.tenant_id == source.tenant_id)
            .where(WorkspaceSource.id != source.id)
            .where(WorkspaceSource.status == "approved")
            .where(WorkspaceSource.claims_status == "done")
        )
        if source.project_id is None:
            others = others.where(WorkspaceSource.client_id == source.client_id)
        else:
            same_project = WorkspaceSource.project_id == source.project_id
            if source.process_id:
                same_project = and_(
                    same_project,
                    or_(WorkspaceSource.process_id.is_(None), WorkspaceSource.process_id == source.process_id),
                )
            others = others.where(or_(same_project, client_wide))
        return (
            _claims_as_input(session, [source]),
            _claims_as_input(
                session,
                list(session.execute(others.order_by(WorkspaceSource.id).limit(MAX_RECONCILE_CANDIDATES)).all()),
            ),
        )


def complete_source_reconcile(source_id: str, result: "ReconcileResult") -> int | None:
    """Scrive le relazioni trovate, al posto di quelle di prima, e passa al grafo.

    Returns:
        Quante relazioni sono state scritte, o `None` se la fonte non c'e'.
    """
    with workspace_connection() as session:
        source = tenant_row(session, WorkspaceSource, source_id)
        if source is None:
            return None
        own = select(WorkspaceSourceClaim.id).where(WorkspaceSourceClaim.source_id == source_id)
        session.execute(delete(WorkspaceClaimRelation).where(WorkspaceClaimRelation.claim_id.in_(own)))
        now = now_iso()
        session.add_all(
            WorkspaceClaimRelation(
                tenant_id=source.tenant_id,
                project_id=source.project_id,
                process_id=source.process_id,
                claim_id=relation.claim_id,
                other_claim_id=relation.other_claim_id,
                kind=relation.kind,
                declared_type=relation.declared_type,
                divergence_type=relation.divergence_type,
                reasons_json=json.dumps(list(relation.reasons), ensure_ascii=False),
                explanation=relation.explanation,
                prompt_version=result.prompt_version,
                created_at=now,
            )
            for relation in result.relations
        )
        source.reconcile_status = "done"
        source.reconcile_next_attempt_at = None
        source.reconcile_error = (
            f"Confrontata con le prime affermazioni: {result.existing_left_out} rimaste fuori per la lunghezza."
            if result.existing_left_out
            else None
        )
        _queue_graph(source)
        session.flush()
        return len(result.relations)


def fail_source_reconcile(source_id: str, *, error: str, permanent: bool) -> None:
    """Un confronto non riuscito: si riprova con backoff, ma non per sempre.

    Quando si smette di riprovare, le affermazioni vanno comunque nel grafo:
    senza confronto, ma non ferme.
    """
    with workspace_connection() as session:
        source = tenant_row(session, WorkspaceSource, source_id)
        if source is None:
            return
        source.reconcile_error = str(error)[:2000]
        if permanent or source.reconcile_attempts >= RECONCILE_MAX_ATTEMPTS:
            source.reconcile_status = "failed"
            source.reconcile_next_attempt_at = None
            _queue_graph(source)
        else:
            delay = RECONCILE_BACKOFF_SECONDS * (2 ** max(0, source.reconcile_attempts - 1))
            source.reconcile_next_attempt_at = (datetime.now(UTC) + timedelta(seconds=delay)).isoformat(
                timespec="seconds"
            )
        session.flush()


def _relations_touching(session, source_id: str) -> list[WorkspaceClaimRelation]:
    own = select(WorkspaceSourceClaim.id).where(WorkspaceSourceClaim.source_id == source_id)
    return list(
        session.execute(
            select(WorkspaceClaimRelation)
            .where(or_(WorkspaceClaimRelation.claim_id.in_(own), WorkspaceClaimRelation.other_claim_id.in_(own)))
            .order_by(WorkspaceClaimRelation.id)
        ).scalars().all()
    )


def _sides(session, relation: WorkspaceClaimRelation, source_id: str):
    """Le due affermazioni della relazione: prima quella di `source_id`."""
    claim = session.get(WorkspaceSourceClaim, relation.claim_id)
    other = session.get(WorkspaceSourceClaim, relation.other_claim_id)
    return (claim, other) if claim.source_id == source_id else (other, claim)


def graph_divergences(source_id: str) -> list[dict]:
    """Le divergenze di questa fonte da portare nel grafo come contraddizioni.

    Una divergenza tocca due file: la scrive la coda del grafo del file che ci
    arriva per secondo, quando il Claim dell'altro esiste gia'. Per questo si
    guardano le relazioni in tutte e due le direzioni.

    Returns:
        Per ogni divergenza: `relation_id`, `ordinal` (l'affermazione di questa
        fonte), `other_kg_claim_id`, `divergence_type`, gli enunciati e i nomi
        dei due file.
    """
    with workspace_connection() as session:
        if tenant_row(session, WorkspaceSource, source_id) is None:
            return []
        out = []
        for relation in _relations_touching(session, source_id):
            if relation.kind != "divergence":
                continue
            mine, theirs = _sides(session, relation, source_id)
            if not theirs.kg_claim_id:
                continue
            out.append(
                {
                    "relation_id": relation.id,
                    "ordinal": mine.ordinal,
                    "other_kg_claim_id": theirs.kg_claim_id,
                    "divergence_type": relation.divergence_type or "tension_to_explore",
                    "statement": mine.statement,
                    "other_statement": theirs.statement,
                    "source_name": session.get(WorkspaceSource, mine.source_id).name,
                    "other_source_name": session.get(WorkspaceSource, theirs.source_id).name,
                }
            )
        return out


def record_graph_ids(source_id: str, *, claim_ids: dict[int, str], contradiction_ids: dict[int, str]) -> None:
    """Annota i Claim e le contraddizioni che la coda del grafo ha scritto."""
    with workspace_connection() as session:
        if tenant_row(session, WorkspaceSource, source_id) is None:
            return
        for claim in session.execute(
            select(WorkspaceSourceClaim).where(WorkspaceSourceClaim.source_id == source_id)
        ).scalars():
            claim.kg_claim_id = claim_ids.get(claim.ordinal)
        for relation_id, contradiction_id in contradiction_ids.items():
            relation = session.get(WorkspaceClaimRelation, relation_id)
            if relation is not None:
                relation.kg_contradiction_id = contradiction_id
        session.flush()


def list_claim_relations(source_id: str) -> list[dict]:
    """Corroborazioni e divergenze di una fonte, ognuna con le due affermazioni.

    Ogni lato porta la sua porzione e la sua citazione: un conflitto si guarda
    con le due evidenze davanti, non con un riassunto.
    """
    from backend.memory.provenance import DIVERGENCE_LABEL_IT

    def side(claim: WorkspaceSourceClaim, source: WorkspaceSource) -> dict:
        return {
            "claim_id": claim.id,
            "source_id": source.id,
            "source_name": source.name,
            "statement": claim.statement,
            "anchor_ref": claim.anchor_ref,
            "quote": claim.quote,
            "quote_verified": claim.quote_verified,
        }

    with workspace_connection() as session:
        if tenant_row(session, WorkspaceSource, source_id) is None:
            return []
        out = []
        for relation in _relations_touching(session, source_id):
            mine, theirs = _sides(session, relation, source_id)
            out.append(
                {
                    "id": relation.id,
                    "kind": relation.kind,
                    "divergence_type": relation.divergence_type,
                    "divergence_label": DIVERGENCE_LABEL_IT.get(relation.divergence_type or ""),
                    "declared_type": relation.declared_type,
                    "reasons": json.loads(relation.reasons_json or "[]"),
                    "explanation": relation.explanation,
                    "claim": side(mine, session.get(WorkspaceSource, mine.source_id)),
                    "other": side(theirs, session.get(WorkspaceSource, theirs.source_id)),
                }
            )
        return out


GRAPH_MAX_ATTEMPTS = 3


GRAPH_BACKOFF_SECONDS = 60


GRAPH_LEASE_SECONDS = 120


def due_source_graph(limit: int = 1, *, only_tenant_id: str | None = None) -> list[dict]:
    """Prende in carico le fonti le cui affermazioni vanno portate nel grafo.

    Il tentativo si conta alla presa in carico, come nelle altre code.
    """
    now = now_iso()
    lease_until = (datetime.now(UTC) + timedelta(seconds=GRAPH_LEASE_SECONDS)).isoformat(timespec="seconds")
    with workspace_connection() as session:
        statement = (
            select(WorkspaceSource)
            .where(WorkspaceSource.graph_status == "pending")
            .where(WorkspaceSource.graph_next_attempt_at <= now)
            .order_by(WorkspaceSource.graph_next_attempt_at)
            .limit(max(1, int(limit)))
            .with_for_update(skip_locked=True)
        )
        if only_tenant_id:
            statement = statement.where(WorkspaceSource.tenant_id == only_tenant_id)
        claimed = []
        for row in session.execute(statement).scalars().all():
            if row.graph_attempts >= GRAPH_MAX_ATTEMPTS:
                row.graph_status = "failed"
                row.graph_next_attempt_at = None
                row.graph_error = row.graph_error or "Il passaggio nel grafo si e' interrotto troppe volte."
                continue
            row.graph_attempts += 1
            row.graph_next_attempt_at = lease_until
            claimed.append(
                {
                    "id": row.id,
                    "tenant_id": row.tenant_id,
                    "name": row.name,
                    "project_id": row.project_id,
                    "client_id": row.client_id,
                    "process_id": row.process_id,
                    "content_hash": row.content_hash,
                    "byte_size": row.byte_size,
                }
            )
        session.flush()
        return claimed


def complete_source_graph(source_id: str) -> None:
    with workspace_connection() as session:
        source = tenant_row(session, WorkspaceSource, source_id)
        if source is None:
            return
        source.graph_status = "done"
        source.graph_next_attempt_at = None
        source.graph_error = None
        session.flush()


def fail_source_graph(source_id: str, *, error: str, permanent: bool) -> None:
    """Un passaggio nel grafo non riuscito: si riprova con backoff, ma non per sempre."""
    with workspace_connection() as session:
        source = tenant_row(session, WorkspaceSource, source_id)
        if source is None:
            return
        source.graph_error = str(error)[:2000]
        if permanent or source.graph_attempts >= GRAPH_MAX_ATTEMPTS:
            source.graph_status = "failed"
            source.graph_next_attempt_at = None
        else:
            delay = GRAPH_BACKOFF_SECONDS * (2 ** max(0, source.graph_attempts - 1))
            source.graph_next_attempt_at = (datetime.now(UTC) + timedelta(seconds=delay)).isoformat(
                timespec="seconds"
            )
        session.flush()


def list_source_claims(source_id: str) -> list[dict]:
    """Le affermazioni di una fonte, nell'ordine in cui sono state estratte."""
    with workspace_connection() as session:
        if tenant_row(session, WorkspaceSource, source_id) is None:
            return []
        rows = session.execute(
            select(WorkspaceSourceClaim)
            .where(WorkspaceSourceClaim.source_id == source_id)
            .where(WorkspaceSourceClaim.tenant_id == tenant_id())
            .order_by(WorkspaceSourceClaim.ordinal)
        ).scalars().all()
        return [
            {
                "id": row.id,
                "source_id": row.source_id,
                "ordinal": row.ordinal,
                "statement": row.statement,
                "segment_ordinal": row.segment_ordinal,
                "anchor_ref": row.anchor_ref,
                "quote": row.quote,
                "quote_verified": row.quote_verified,
                "extracted_at": row.extracted_at,
            }
            for row in rows
        ]


def list_claims_for_sources(source_ids: list[str]) -> list[dict]:
    """Le affermazioni di piu' fonti del tenant corrente, in una sola lettura."""
    if not source_ids:
        return []
    with workspace_connection() as session:
        rows = session.execute(
            select(WorkspaceSourceClaim)
            .where(WorkspaceSourceClaim.source_id.in_(source_ids))
            .where(WorkspaceSourceClaim.tenant_id == tenant_id())
            .order_by(WorkspaceSourceClaim.source_id, WorkspaceSourceClaim.ordinal)
        ).scalars().all()
        return [
            {"id": row.id, "statement": row.statement, "quote": row.quote,
             "quote_verified": row.quote_verified, "source_id": row.source_id}
            for row in rows
        ]


def list_evidence_segments(source_id: str) -> list[dict]:
    """Le porzioni citabili di una fonte, nell'ordine della fonte."""
    with workspace_connection() as session:
        if tenant_row(session, WorkspaceSource, source_id) is None:
            return []
        rows = session.execute(
            select(WorkspaceEvidenceSegment)
            .where(WorkspaceEvidenceSegment.source_id == source_id)
            .where(WorkspaceEvidenceSegment.tenant_id == tenant_id())
            .order_by(WorkspaceEvidenceSegment.ordinal)
        ).scalars().all()
        return [
            {
                "id": row.id,
                "source_id": row.source_id,
                "ordinal": row.ordinal,
                "kind": row.anchor_kind,
                "ref": row.anchor_ref,
                "locator": json.loads(row.locator_json),
                "text": row.text,
                "value_type": row.value_type,
                "value": json.loads(row.value_json) if row.value_json else None,
                "attributes": json.loads(row.attributes_json),
            }
            for row in rows
        ]
