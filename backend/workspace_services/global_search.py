"""Cerca in tutto il workspace: clienti, progetti, processi, fonti.

La lente nella barra in alto non aveva un flusso: si scriveva e non succedeva
niente. Cio' che serve a un consulente con venti incarichi aperti non e' un
filtro in piu' su una lista, ma un modo di saltare a cio' che ha in mente -
"Esaote", "ciclo passivo", "intervista Neri" - senza ricordarsi sotto quale
cliente e quale progetto stia.

Sola lettura, e sempre dentro il tenant corrente. Ogni risultato porta con se'
dove si trova (cliente, progetto) e cosa serve per aprirlo.
"""

from __future__ import annotations

from typing import Literal

from sqlalchemy import Select, and_, case, func, or_, select

from backend.search_text import like_escape, like_patterns, match_rank, search_terms
from backend.security import get_current_tenant_id
from backend.workspace_storage import (
    WorkspaceClient,
    WorkspaceProcess,
    WorkspaceProject,
    WorkspaceSource,
    workspace_connection,
)

ResultKind = Literal["client", "project", "process", "source"]

# A parita' di corrispondenza, l'ordine in cui il lavoro si annida: il cliente
# contiene i progetti, il progetto i processi, il processo le fonti. Chi cerca
# "Esaote" vuole prima il cliente, non la ventesima intervista che lo nomina.
KIND_ORDER: dict[ResultKind, int] = {"client": 0, "project": 1, "process": 2, "source": 3}


def _relevance(column, terms: list[str]):
    """L'ordine di pertinenza, calcolato dal database.

    E' la stessa regola di `match_rank`, scritta in SQL: esatto, poi "comincia
    cosi'" - anche quando la parola cercata apre una parola qualunque del titolo
    ("passivo" su "Ciclo passivo") - poi il resto.

    Deve stare qui e non solo in Python perche' il taglio per tipo
    (`per_kind_limit`) avviene nel database: ordinando per nome, su un cliente
    con trenta processi "Ordini" quello che si chiama esattamente cosi' poteva
    restare fuori dai candidati.
    """
    joined = " ".join(terms)
    first = like_escape(terms[0])
    lowered = func.lower(column)
    return case(
        (lowered == joined, 0),
        (
            or_(
                lowered.like(f"{like_escape(joined)}%", escape="\\"),
                lowered.like(f"{first}%", escape="\\"),
                lowered.like(f"% {first}%", escape="\\"),
            ),
            1,
        ),
        else_=2,
    )


def _terms_match(column, patterns: list[str]):
    """Tutte le parole nella stessa colonna: "ciclo passivo" non e' "ciclo" o "passivo"."""
    return and_(*(func.lower(column).like(pattern, escape="\\") for pattern in patterns))


def _scoped(statement: Select, tenant: str, *models) -> Select:
    for model in models:
        statement = statement.where(model.tenant_id == tenant)
        archived = getattr(model, "archived_at", None)
        if archived is not None:
            statement = statement.where(archived.is_(None))
    return statement


def search_workspace(query: str, *, limit: int = 20, per_kind_limit: int = 25) -> list[dict]:
    """Cerca clienti, progetti, processi e fonti del tenant corrente.

    Restano fuori i record archiviati e quelli che stanno sotto un record
    archiviato: l'archivio ha la sua pagina, e una ricerca che riporta a galla
    un incarico chiuso fa riaprire il lavoro sbagliato.

    Args:
        query: Il testo cercato, non affidabile. Vuoto: nessun risultato, non
            tutto - una ricerca senza parole non e' l'elenco del workspace.
        limit: Quanti risultati restituire in tutto.
        per_kind_limit: Quanti candidati leggere per tipo prima di ordinare.
            Tiene la query a costo fisso su un workspace grande.

    Returns:
        I risultati, i piu' pertinenti per primi, ognuno con `kind`, `id`,
        `title`, il contesto in cui vive e gli id che servono ad aprirlo.
    """
    terms = search_terms(query)
    if not terms:
        return []

    patterns = like_patterns(terms)
    tenant = get_current_tenant_id()
    results: list[dict] = []

    with workspace_connection() as session:
        clients = session.execute(
            _scoped(
                select(WorkspaceClient.id, WorkspaceClient.name, WorkspaceClient.sector)
                .where(_terms_match(WorkspaceClient.name, patterns))
                .order_by(_relevance(WorkspaceClient.name, terms), WorkspaceClient.name)
                .limit(per_kind_limit),
                tenant,
                WorkspaceClient,
            )
        ).all()
        for client_id, name, sector in clients:
            results.append(
                {
                    "kind": "client",
                    "id": client_id,
                    "title": name,
                    "context": sector,
                    "client_id": client_id,
                    "client_name": name,
                }
            )

        projects = session.execute(
            _scoped(
                select(
                    WorkspaceProject.id,
                    WorkspaceProject.name,
                    WorkspaceProject.phase,
                    WorkspaceClient.id,
                    WorkspaceClient.name,
                )
                .join(WorkspaceClient, WorkspaceClient.id == WorkspaceProject.client_id)
                # Anche l'obiettivo: e' li' che sta scritto cosa chiude l'incarico,
                # ed e' spesso l'unica frase che il consulente ricorda.
                .where(
                    or_(
                        _terms_match(WorkspaceProject.name, patterns),
                        _terms_match(WorkspaceProject.objective, patterns),
                    )
                )
                .order_by(_relevance(WorkspaceProject.name, terms), WorkspaceProject.name)
                .limit(per_kind_limit),
                tenant,
                WorkspaceProject,
                WorkspaceClient,
            )
        ).all()
        for project_id, name, phase, client_id, client_name in projects:
            results.append(
                {
                    "kind": "project",
                    "id": project_id,
                    "title": name,
                    "context": f"{client_name} · {phase}",
                    "client_id": client_id,
                    "client_name": client_name,
                    "project_id": project_id,
                    "project_name": name,
                }
            )

        processes = session.execute(
            _scoped(
                select(
                    WorkspaceProcess.id,
                    WorkspaceProcess.name,
                    WorkspaceProcess.stage,
                    WorkspaceProject.id,
                    WorkspaceProject.name,
                    WorkspaceClient.id,
                    WorkspaceClient.name,
                )
                .join(WorkspaceProject, WorkspaceProject.id == WorkspaceProcess.project_id)
                .join(WorkspaceClient, WorkspaceClient.id == WorkspaceProject.client_id)
                .where(_terms_match(WorkspaceProcess.name, patterns))
                .order_by(_relevance(WorkspaceProcess.name, terms), WorkspaceProcess.name)
                .limit(per_kind_limit),
                tenant,
                WorkspaceProcess,
                WorkspaceProject,
                WorkspaceClient,
            )
        ).all()
        for (
            process_id,
            name,
            stage,
            project_id,
            project_name,
            client_id,
            client_name,
        ) in processes:
            results.append(
                {
                    "kind": "process",
                    "id": process_id,
                    "title": name,
                    "context": f"{client_name} · {project_name} · {stage}",
                    "client_id": client_id,
                    "client_name": client_name,
                    "project_id": project_id,
                    "project_name": project_name,
                    "process_id": process_id,
                }
            )

        sources = session.execute(
            _scoped(
                select(
                    WorkspaceSource.id,
                    WorkspaceSource.name,
                    WorkspaceSource.type,
                    WorkspaceSource.process_id,
                    WorkspaceProject.id,
                    WorkspaceProject.name,
                    WorkspaceClient.id,
                    WorkspaceClient.name,
                )
                .join(WorkspaceProject, WorkspaceProject.id == WorkspaceSource.project_id)
                .join(WorkspaceClient, WorkspaceClient.id == WorkspaceProject.client_id)
                # Una fonte di un processo archiviato sta sotto un record
                # archiviato; quella senza processo resta.
                .outerjoin(WorkspaceProcess, WorkspaceProcess.id == WorkspaceSource.process_id)
                .where(WorkspaceProcess.archived_at.is_(None))
                .where(_terms_match(WorkspaceSource.name, patterns))
                .order_by(_relevance(WorkspaceSource.name, terms), WorkspaceSource.name)
                .limit(per_kind_limit),
                tenant,
                WorkspaceSource,
                WorkspaceProject,
                WorkspaceClient,
            )
        ).all()
        for (
            source_id,
            name,
            source_type,
            process_id,
            project_id,
            project_name,
            client_id,
            client_name,
        ) in sources:
            results.append(
                {
                    "kind": "source",
                    "id": source_id,
                    "title": name,
                    "context": f"{client_name} · {project_name}",
                    "client_id": client_id,
                    "client_name": client_name,
                    "project_id": project_id,
                    "project_name": project_name,
                    "process_id": process_id,
                    "source_type": source_type,
                }
            )

    # Prima quanto il nome corrisponde, poi quanto il record e' "grande": un
    # cliente che si chiama esattamente come la ricerca sta sopra a un progetto
    # che la contiene a meta' frase.
    results.sort(
        key=lambda item: (
            match_rank(item["title"], terms),
            KIND_ORDER[item["kind"]],
            item["title"].casefold(),
        )
    )
    return results[: max(1, int(limit))]
