# Immagine di DeliR: backend FastAPI + frontend compilato, un solo container.
#
#   docker buildx build --platform linux/arm64 -t delir:dev .      # VM Oracle A1
#   docker build -t delir:dev .                                    # macchina locale
#
# Avvio: ops/docker/entrypoint.sh (migrazioni sotto lock, poi uvicorn).
# Configurazione solo da variabili d'ambiente: nell'immagine non c'e' nessun
# segreto e nessun .env.

# --- 1. Frontend: file statici, uguali per ogni processore -------------------
# Gira sull'architettura di chi costruisce (niente emulazione ARM): e' lo
# stadio piu' lento, e il suo risultato non dipende dalla piattaforma.
FROM --platform=$BUILDPLATFORM node:24-bookworm-slim AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --legacy-peer-deps --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- 2. Dipendenze Python, le versioni esatte di uv.lock ---------------------
FROM python:3.14-slim-bookworm AS deps
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project

# --- 3. Runtime: solo cio' che serve per girare ------------------------------
FROM python:3.14-slim-bookworm AS runtime
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    RUN_MIGRATIONS_ON_STARTUP=false \
    DELIR_ENVIRONMENT=prod \
    OPENBLAS_NUM_THREADS=1
WORKDIR /app

RUN useradd --system --uid 10001 --home-dir /app delir \
    && mkdir -p /app/data \
    && chown delir /app/data

COPY --from=deps /opt/venv /opt/venv
COPY backend/ backend/
COPY migrations/ migrations/
COPY migrations_workspace/ migrations_workspace/
COPY alembic.ini alembic_workspace.ini ./
COPY scripts/migrate.py scripts/migrate.py
COPY --from=frontend /src/frontend/dist frontend/dist
COPY --chmod=0755 ops/docker/entrypoint.sh /usr/local/bin/delir-entrypoint

USER delir
# I file caricati dal consulente e la cache degli episodi: fuori dal container.
VOLUME ["/app/data"]
EXPOSE 8000

# Pronto = database raggiungibili e a head, non solo processo vivo. Il primo
# avvio migra entrambi i database: start-period largo, o il container risulta
# "unhealthy" mentre sta solo aggiornando lo schema.
HEALTHCHECK --interval=30s --timeout=10s --start-period=180s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=8).status == 200 else 1)"]

ENTRYPOINT ["/usr/local/bin/delir-entrypoint"]
