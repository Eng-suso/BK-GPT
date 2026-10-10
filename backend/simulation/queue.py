"""La coda delle simulazioni su Postgres (P0.3).

Un run entra in coda con tutto cio' che serve per eseguirlo (scenario, BPMN
normalizzato, richiesta) e non dipende piu' dal processo che l'ha ricevuto:

- **ammissione**: oltre ``simulation_max_queued_runs`` run in attesa la richiesta
  riceve 429; sotto, il run aspetta il suo turno invece di essere rifiutato;
- **presa**: ``claim_next_run`` serializza le prese con un lock advisory, conta i
  run in corso in tutto il deploy (Prosimos e' uno solo) e prende il piu' vecchio
  in coda con ``FOR UPDATE SKIP LOCKED``. Due processi non prendono lo stesso run
  e insieme non superano ``simulation_max_concurrent_runs``;
- **battito**: chi esegue aggiorna ``heartbeat_at``. Un run che tace da tre
  battiti e' di un processo morto: torna in coda, o fallisce dopo ``MAX_ATTEMPTS``
  prese con un messaggio per il consulente.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from backend.schemas.simulation import SimSlaConfig, SimulationQueueView
from backend.settings import settings
from backend.simulation.costs import FixedCosts
from backend.simulation.models import ProsimosScenario
from backend.workspace_storage import WorkspaceSimulationRun, workspace_connection

logger = logging.getLogger(__name__)

#: Quante volte un run puo' essere preso prima di arrendersi.
MAX_ATTEMPTS = 2
#: Battiti mancati prima di dichiarare morto chi esegue.
MISSED_BEATS = 3
#: Chiave del lock advisory che serializza le prese (``"sim-queue"`` in esadecimale).
_CLAIM_LOCK = 0x73696D2D7175

STALE_RUN_ERROR = (
    "La simulazione non e' arrivata in fondo: il servizio si e' fermato due volte "
    "mentre girava. Rilanciala, e se succede ancora segnalalo."
)
LEGACY_STALE_RUN_ERROR = (
    "La simulazione non e' arrivata in fondo: il servizio si e' fermato mentre "
    "girava. Rilanciala."
)


class SimulationQueueFull(RuntimeError):
    """La coda e' piena: la richiesta e' giusta, il momento no (429)."""


@dataclass(frozen=True, slots=True)
class ClaimedRun:
    """Un run preso dalla coda, con tutto cio' che serve per eseguirlo."""

    run_id: int
    tenant_id: str
    worker_id: str
    bpmn_xml: str
    scenario: ProsimosScenario
    total_cases: int
    start_date: str | None
    seed: int | None
    # L'obiettivo di servizio dello scenario (SIM-13), se il consulente l'ha dato.
    sla: SimSlaConfig | None = None
    # SIM-10: i costi fissi dello scenario, sommati al costo delle risorse a fine run.
    fixed_costs: FixedCosts = field(default_factory=FixedCosts)
    # SIM-03: i primi casi, che trovano il sistema vuoto, restano fuori dai KPI.
    warmup_cases: int = 0


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _queued():
    return (WorkspaceSimulationRun.status == "pending") & WorkspaceSimulationRun.started_at.is_(None)


def _running():
    return (WorkspaceSimulationRun.status == "pending") & WorkspaceSimulationRun.started_at.is_not(None)


def admit(session: Session) -> None:
    """Dentro la transazione che inserisce il run: c'e' posto in coda?

    Il lock advisory e' lo stesso delle prese, cosi' due ammissioni insieme non
    superano il limite contando la stessa coda.
    """
    session.execute(select(func.pg_advisory_xact_lock(_CLAIM_LOCK)))
    reap_stale_runs(session)
    waiting = session.execute(select(func.count()).select_from(WorkspaceSimulationRun).where(_queued())).scalar_one()
    if waiting >= settings.simulation_max_queued_runs:
        raise SimulationQueueFull(
            f"Ci sono gia' {waiting} simulazioni in attesa, il massimo della coda. "
            "Aspetta che ne parta qualcuna e rilancia."
        )


def reap_stale_runs(session: Session) -> list[int]:
    """Rimette in coda (o chiude) i run il cui esecutore ha smesso di battere.

    Si chiama dentro le transazioni di chi legge o prende un run: un processo
    morto si scopre alla prima occhiata, senza un servizio in piu'.
    """
    cutoff = datetime.now(UTC) - timedelta(seconds=settings.simulation_heartbeat_seconds * MISSED_BEATS)
    legacy_cutoff = datetime.now(UTC) - timedelta(seconds=settings.prosimos_timeout_seconds + 120.0)
    touched: list[int] = []
    # SKIP LOCKED: una riga che un altro sta toccando (una presa, un battito) non si giudica ora.
    stale = select(WorkspaceSimulationRun).where(_running()).with_for_update(skip_locked=True)
    for run in session.execute(stale).scalars():
        beat = _parse(run.heartbeat_at)
        if beat is None:
            # Run anteriori alla coda: non battono, si giudicano dall'avvio come prima.
            started = _parse(run.started_at)
            if started is not None and started > legacy_cutoff:
                continue
            run.status, run.error, run.completed_at = "failed", LEGACY_STALE_RUN_ERROR, now_iso()
        elif beat > cutoff:
            continue
        elif run.bpmn_xml and run.attempts < MAX_ATTEMPTS:
            run.started_at = run.heartbeat_at = run.worker_id = None
        else:
            run.status, run.error, run.completed_at = "failed", STALE_RUN_ERROR, now_iso()
        touched.append(run.id)
    if touched:
        session.flush()
        logger.warning("simulazioni senza battito, rimesse in coda o chiuse: %s", touched)
    return touched


def claim_next_run(worker_id: str) -> ClaimedRun | None:
    """Il run piu' vecchio in coda, se c'e' posto nel motore; altrimenti ``None``."""
    with workspace_connection() as session:
        session.execute(select(func.pg_advisory_xact_lock(_CLAIM_LOCK)))
        reap_stale_runs(session)
        running = session.execute(select(func.count()).select_from(WorkspaceSimulationRun).where(_running())).scalar_one()
        if running >= settings.simulation_max_concurrent_runs:
            return None
        run = session.execute(
            select(WorkspaceSimulationRun)
            .where(_queued())
            .order_by(WorkspaceSimulationRun.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        ).scalars().first()
        if run is None:
            return None
        stamp = now_iso()
        run.started_at = run.heartbeat_at = stamp
        run.worker_id = worker_id
        run.attempts = (run.attempts or 0) + 1
        session.flush()
        request = json.loads(run.request_json or "{}")
        payload = json.loads(run.scenario_json or "{}")
        return ClaimedRun(
            run_id=run.id,
            tenant_id=run.tenant_id,
            worker_id=worker_id,
            bpmn_xml=run.bpmn_xml or "",
            scenario=ProsimosScenario(
                payload=payload,
                task_count=len(payload.get("task_resource_distribution", [])),
                gateway_count=len(payload.get("gateway_branching_probabilities", [])),
                model=json.loads(run.model_json) if run.model_json else None,
            ),
            total_cases=int(request.get("total_cases") or 100),
            start_date=request.get("start_date"),
            seed=request.get("seed"),
            # Rivalidato: la richiesta salvata torna dal database, non dal client.
            sla=SimSlaConfig.model_validate(request["sla"]) if request.get("sla") else None,
            fixed_costs=FixedCosts(
                per_execution={
                    task["element_id"]: float(task["fixed_cost"])
                    for task in request.get("tasks") or []
                    if task.get("fixed_cost")
                },
                per_case=float(request.get("case_fixed_cost") or 0.0),
            ),
            warmup_cases=int(request.get("warmup_cases") or 0),
        )


def beat(run_id: int, worker_id: str) -> bool:
    """Aggiorna il battito; ``False`` se il run non e' piu' di questo esecutore."""
    with workspace_connection() as session:
        # Un UPDATE condizionato: se lo spazzino ha appena rimesso il run in coda,
        # il battito non lo riporta in vita.
        updated = session.execute(
            update(WorkspaceSimulationRun)
            .where(WorkspaceSimulationRun.id == run_id)
            .where(_running())
            .where(WorkspaceSimulationRun.worker_id == worker_id)
            .values(heartbeat_at=now_iso())
        )
        return updated.rowcount == 1


def queue_view(session: Session, run: WorkspaceSimulationRun) -> SimulationQueueView | None:
    """Per un run ``pending``: in coda (con la posizione) o in corso. ``None`` altrimenti."""
    if run.status != "pending":
        return None
    if run.started_at is not None:
        return SimulationQueueView(state="running")
    ahead = session.execute(
        select(func.count()).select_from(WorkspaceSimulationRun).where(_queued()).where(WorkspaceSimulationRun.id < run.id)
    ).scalar_one()
    return SimulationQueueView(state="queued", position=int(ahead) + 1)
