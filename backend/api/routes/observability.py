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
