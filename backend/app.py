import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path


from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response

from backend.api.errors import setup_api_error_handlers
from backend.api.routes.audio import router as audio_router
from backend.api.routes.chat import router as chat_router
from backend.api.routes.memory import router as memory_router
from backend.api.routes.observability import router as observability_router
from backend.api.routes.simulation import router as simulation_router
from backend.api.routes.workspace import router as workspace_router
from backend.security import (
    assert_allowed_tenant,
    normalize_tenant_id,
    reset_current_tenant_id,
    set_current_tenant_id,
)
from backend.settings import settings

from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    from backend.workers.supervisor import run_queue_workers

    worker_task = asyncio.create_task(run_queue_workers(), name="queue_workers")
    try:
        yield
    finally:
        worker_task.cancel()
        try:
            await worker_task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass


app = FastAPI(lifespan=lifespan)
setup_api_error_handlers(app)


def configured_cors_origins() -> list[str]:
    if not settings.delir_auth_enabled:
        return ["*"]

    origins = [
        origin.strip()
        for origin in settings.delir_cors_origins.split(",")
        if origin.strip()
    ]
    return origins or ["http://127.0.0.1:3030", "http://localhost:3030"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=configured_cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def tenant_context_middleware(request: Request, call_next):
    try:
        tenant_id = normalize_tenant_id(request.headers.get("X-DeliR-Tenant-ID"))
        assert_allowed_tenant(tenant_id)
    except HTTPException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=exc.headers,
        )

    token = set_current_tenant_id(tenant_id)
    try:
        return await call_next(request)
    finally:
        reset_current_tenant_id(token)


app.include_router(workspace_router)
app.include_router(simulation_router)
app.include_router(memory_router)
app.include_router(observability_router)
app.include_router(chat_router)
app.include_router(audio_router)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
DIST_DIR = FRONTEND_DIR / "dist"

if DIST_DIR.exists() and (DIST_DIR / "index.html").exists():
    FRONTEND_INDEX = DIST_DIR / "index.html"
    if (DIST_DIR / "assets").exists():
        app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")
else:
    FRONTEND_INDEX = FRONTEND_DIR / "index.html"

if (FRONTEND_DIR / "styles").exists():
    app.mount("/styles", StaticFiles(directory=FRONTEND_DIR / "styles"), name="styles")
if (FRONTEND_DIR / "src").exists():
    app.mount("/src", StaticFiles(directory=FRONTEND_DIR / "src"), name="src")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def frontend():
    return FileResponse(FRONTEND_INDEX, headers={"Cache-Control": "no-store"})


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


