from fastapi import APIRouter, Depends

from backend.services.eval_runner import run_observability_smoke_eval
from backend.services.trace_recorder import get_trace
from backend.security import require_principal


router = APIRouter(prefix="/v1", tags=["observability"], dependencies=[Depends(require_principal)])


@router.get("/observability/traces/{trace_id}")
def get_observability_trace(trace_id: str):
    return {"trace_id": trace_id, "events": [event.model_dump() for event in get_trace(trace_id)]}


@router.post("/evals/observability-smoke")
def run_observability_eval():
    return run_observability_smoke_eval()


@router.get("/observability/queues")
def get_queue_health():
    """Stato delle code di proiezione (canonical -> Neo4j / Mem0). `stuck` > 0
    = payload falliti troppe volte, da ispezionare (`last_error` in tabella)."""
    from backend.settings import settings

    if not settings.canonical_worker_url:
        return {"status": "not_configured"}
    from backend.workers import graph_worker, mem0_worker

    out: dict = {"status": "ok"}
    for name, worker in (("graph_outbox", graph_worker), ("mem0_projection_log", mem0_worker)):
        try:
            out[name] = worker.queue_stats()
        except Exception as exc:  # noqa: BLE001
            out[name] = {"error": str(exc)}
    return out
