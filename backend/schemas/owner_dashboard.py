"""Cio' che il cruscotto del responsabile del processo mostra, e niente di piu'.

Il cruscotto lo legge una persona fuori dallo studio di consulenza. Questi
modelli sono l'elenco chiuso di cio' che le arriva: niente citazioni dalle
interviste, niente note interne nel disegno, niente dettagli delle domande
aperte, niente identificativi tecnici oltre a quelli che servono a legare una
modifica al suo passo.
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DashboardProcess(_Closed):
    name: str
    owner: str
    status: str
    stage: str


class DashboardChange(_Closed):
    id: str
    node_id: str
    node_name: str
    title: str
    #: Il perche' della modifica, scritto dal consulente per il cliente.
    detail: str
    created_at: str


class DashboardOpenPoint(_Closed):
    id: str
    node_id: str
    node_name: str
    title: str
    kind: Literal["clarification", "deferred"]
    created_at: str


class DashboardVersion(_Closed):
    id: int
    change_summary: str
    created_at: str


class DashboardResults(_Closed):
    """I numeri attesi dall'ultima simulazione conclusa."""

    scenario_name: str
    completed_at: str | None
    cycle_avg_seconds: float
    waiting_avg_seconds: float
    cost_per_case: float


class OwnerDashboard(_Closed):
    process: DashboardProcess
    project_name: str
    client_name: str
    #: Il disegno, senza documentazione, estensioni e coordinate grafiche.
    xml: str | None
    changes: list[DashboardChange]
    open_points: list[DashboardOpenPoint]
    versions: list[DashboardVersion]
    results: DashboardResults | None
    generated_at: str


class OwnerLinkStatus(_Closed):
    """Lo stato del link per il consulente. Il codice non c'e': esiste solo alla creazione."""

    active: bool
    created_at: str | None = None
    expires_at: str | None = None
    last_viewed_at: str | None = None
    view_count: int = 0


class OwnerLinkCreated(_Closed):
    """La sola risposta che contiene il codice del link, una volta."""

    token: str
    created_at: str
    expires_at: str
