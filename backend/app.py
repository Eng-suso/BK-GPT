from pathlib import Path


from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response

from backend.api.errors import setup_api_error_handlers
from backend.api.routes.audio import router as audio_router
from backend.api.routes.chat import router as chat_router
from backend.api.routes.memory import router as memory_router
from backend.api.routes.observability import router as observability_router
from backend.api.routes.workspace import router as workspace_router

from fastapi.staticfiles import StaticFiles

app = FastAPI()
setup_api_error_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(workspace_router)
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


