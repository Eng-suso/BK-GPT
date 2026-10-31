import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal


from anyio import to_thread
from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler as default_http_exception_handler
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.responses import FileResponse, JSONResponse, Response

from backend.api.errors import setup_api_error_handlers
from backend.api.routes.audio import router as audio_router
from backend.api.routes.identity import router as identity_router
from backend.api.routes.chat import router as chat_router
from backend.api.routes.memory import router as memory_router
from backend.api.routes.observability import router as observability_router
from backend.api.routes.simulation import router as simulation_router
from backend.api.routes.simulation_scenarios import router as simulation_scenarios_router
from backend.api.routes.eventlog import router as eventlog_router
from backend.api.routes.shared import router as shared_router
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


#: Gli ambienti in cui partire senza autenticazione non e' una scelta, e' un
#: incidente: la porta resta aperta e nessuno se ne accorge finche' non entra
#: qualcuno. La lista dice dove partire scoperti e' lecito, non dove e' vietato:
#: elencare gli ambienti da proteggere lascerebbe passare tutto il resto, e
#: `DELIR_ENVIRONMENT=produzione` - la parola giusta, in italiano - sarebbe un
#: deploy aperto per un refuso.
OPEN_ENVIRONMENTS = {"dev", "local", "test"}


def assert_environment_is_defensible() -> Literal["open", "guarded"]:
    """Rifiuta di avviare un ambiente dichiarato vero senza autenticazione.

    Con `delir_auth_enabled` a falso il prodotto accetta qualunque chiamata, con
    CORS `*` e `is_admin` acceso per tutti - cancellazioni comprese. In
    sviluppo e' comodo ed e' il default. In un ambiente dichiarato staging o
    prod e' un deploy senza porta, e il difetto di prima era che non lo diceva
    nessuno: partiva e basta.

    Returns:
        Literal["open", "guarded"]: `"guarded"` quando una richiesta deve
            portare una credenziale, `"open"` quando chiunque puo' chiamare.
            E' un valore e non solo una riga di log, cosi' si puo' verificare
            in un test e, domani, mostrare in `/health`.

    Raises:
        RuntimeError: Quando l'ambiente e' dichiarato vero e l'autenticazione e'
            spenta, o e' accesa e manca il token.
    """
    environment = (settings.delir_environment or "dev").strip().lower()

    if not settings.delir_auth_enabled and environment not in OPEN_ENVIRONMENTS:
        permessi = ", ".join(sorted(OPEN_ENVIRONMENTS))
        raise RuntimeError(
            f"DELIR_ENVIRONMENT={environment} con DELIR_AUTH_ENABLED spento: "
            "il prodotto accetterebbe qualunque chiamata, da qualunque origine, "
            "con permessi di amministratore. Accendi l'autenticazione, oppure "
            f"dichiara uno degli ambienti aperti ({permessi}) se questa e' "
            "davvero una macchina di sviluppo."
        )

    if settings.delir_auth_enabled and not (settings.delir_api_token or "").strip():
        raise RuntimeError(
            "DELIR_AUTH_ENABLED acceso senza DELIR_API_TOKEN: ogni richiesta "
            "riceverebbe 503, che sembra un guasto e invece e' configurazione."
        )

    if not settings.delir_auth_enabled:
        logger.warning(
            "Autenticazione spenta (DELIR_ENVIRONMENT=%s): CORS aperto a tutti e "
            "permessi di amministratore a chiunque chiami. Va bene solo su una "
            "macchina di sviluppo.",
            environment,
        )
        return "open"

    return "guarded"


def size_request_threadpool() -> int:
    """Dichiara quante richieste sincrone possono essere in lavorazione insieme.

    Settantatre rotte su settantasei sono `def` e non `async def`: Starlette le
    esegue nel threadpool di anyio, il cui default e' 40 e non lo aveva scelto
    nessuno. Un turno di chat occupa un posto per tutta la sua durata (fino a
    `agent_run_deadline_seconds`, 90 secondi), una simulazione fino a
    `prosimos_timeout_seconds`: con quaranta turni insieme l'intera API si
    fermava, e prima di questa versione si fermava anche `/health`.

    Il numero non risolve la causa - le rotte lente restano sincrone - ma smette
    di essere un caso: si sceglie guardando quanti turni lenti si vogliono
    reggere, e si puo' alzare senza toccare il codice.

    Returns:
        int: I posti configurati.
    """
    limiter = to_thread.current_default_thread_limiter()
    limiter.total_tokens = max(8, int(settings.api_worker_threads))
    logger.info("threadpool delle richieste: %d posti", limiter.total_tokens)
    return limiter.total_tokens


@asynccontextmanager
async def lifespan(_app: FastAPI):
    assert_environment_is_defensible()
    size_request_threadpool()

    from backend.local_store import ensure_schema
    from backend.workers.simulation_worker import run_simulation_queue
    from backend.workers.supervisor import run_queue_workers

    if settings.workspace_database_url:
        await asyncio.to_thread(ensure_schema)  # migra il DB operativo a head

    worker_task = asyncio.create_task(run_queue_workers(), name="queue_workers")
    # La coda delle simulazioni gira sempre: e' il prodotto, non una proiezione.
    simulation_task = asyncio.create_task(run_simulation_queue(), name="simulation_queue")
    try:
        yield
    finally:
        simulation_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await simulation_task
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
    # Senza questa riga il browser vede le intestazioni ma non le lascia
    # leggere al codice della pagina: l'elenco saprebbe di essere tagliato e
    # non potrebbe dirlo.
    expose_headers=["X-DeliR-Total", "X-DeliR-Returned", "X-DeliR-Limit", "X-Request-ID"],
)


@app.middleware("http")
async def tenant_context_middleware(request: Request, call_next):
    # Il cliente che apre il link non manda lo spazio di lavoro: lo decide il
    # link stesso, nel servizio. Qui non c'e' nulla da controllare.
    if request.url.path.startswith("/v1/shared/"):
        return await call_next(request)
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
app.include_router(shared_router)
app.include_router(simulation_router)
app.include_router(simulation_scenarios_router)
app.include_router(eventlog_router)
app.include_router(memory_router)
app.include_router(observability_router)
app.include_router(identity_router)
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
async def health():
    """Dice che il processo risponde, anche quando e' occupato.

    `async` non e' un dettaglio: una rotta sincrona viene eseguita nel
    threadpool, lo stesso che serve i turni di chat e le simulazioni. Con quei
    posti tutti occupati - ed e' esattamente il momento in cui qualcuno guarda
    `/health` - la risposta restava in coda e il controllo scadeva: il processo
    veniva dichiarato morto mentre stava lavorando. Qui gira nell'event loop,
    quindi risponde sempre.
    """
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def frontend():
    return FileResponse(FRONTEND_INDEX, headers={"Cache-Control": "no-store"})


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


#: Il primo pezzo dei percorsi che non sono pagine: un `GET /v1/...` sbagliato
#: deve ricevere il suo 404, non la pagina dell'app.
NOT_PAGE_ROOTS = {"v1", "chat", "health", "docs", "redoc", "openapi.json", "assets", "src", "styles"}
PAGE_HEADERS = {"Cache-Control": "no-store"}
#: Il cruscotto che il consulente manda al suo cliente: il codice del link sta
#: dopo `#`, e la pagina non deve passarlo a nessuno ne' finire in un indice.
SHARE_PAGE_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Robots-Tag": "noindex, nofollow",
}


def built_frontend_file(path: str) -> Path | None:
    """Un file del build (`share.html`, `favicon.svg`, ...), mai fuori dalla sua cartella."""
    if not DIST_DIR.is_dir():
        return None
    root = DIST_DIR.resolve()
    candidate = (root / path.lstrip("/")).resolve()
    if root not in candidate.parents or not candidate.is_file():
        return None
    return candidate


def is_app_page(path: str) -> bool:
    """`/projects/abc` e' una pagina di React; `/v1/...` e `/x.js` non lo sono."""
    parts = [part for part in path.split("/") if part]
    if not parts:
        return True
    return parts[0] not in NOT_PAGE_ROOTS and "." not in parts[-1]


@app.exception_handler(StarletteHTTPException)
async def frontend_page_fallback(request: Request, exc: StarletteHTTPException):
    """Le pagine dell'app si aprono anche dopo un refresh o da un link salvato.

    In sviluppo ci pensa Vite. In produzione le serve il backend, che conosceva
    solo `/`: ogni altra pagina dava 404, e il link del cruscotto per il
    cliente (`/share.html#codice`) non si apriva. Qui arrivano solo i 404 di
    instradamento - nessuna rotta corrisponde - di un `GET`; le API che dicono
    "non trovato" da sole passano dal gestore di `backend.api.errors`, e ogni
    altro caso riceve la risposta di sempre.
    """
    if exc.status_code == 404 and request.method in {"GET", "HEAD"}:
        path = request.url.path
        built = built_frontend_file(path)
        if built is not None:
            if built.name == "share.html":
                return FileResponse(built, headers=SHARE_PAGE_HEADERS)
            headers = PAGE_HEADERS if built.suffix == ".html" else None
            return FileResponse(built, headers=headers)
        if is_app_page(path):
            return FileResponse(FRONTEND_INDEX, headers=PAGE_HEADERS)
    return await default_http_exception_handler(request, exc)


