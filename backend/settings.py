import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.6-luna"
    openai_transcription_model: str = "gpt-4o-transcribe-diarize"
    openai_live_transcription_model: str = "gpt-realtime-whisper"

    tavily_api_key: str | None = None

    mem0_api_key: str | None = None
    mem0_user_id: str = "local-consultant"

    # --- Mem0 OSS self-hosted (D1) ---------------------------------------
    # DSN del database mem0 isolato (ruolo delir_mem0). Vuoto = Mem0 disattivato.
    mem0_database_url: str | None = None
    mem0_collection: str = "delir_memories"
    mem0_history_db_path: str = "data/mem0_history.db"
    # modello per l'estrazione fatti di Mem0: serve JSON mode. Override se il
    # tuo account non ha gpt-4o-mini.
    mem0_llm_model: str = "gpt-4o-mini"
    mem0_embedder_model: str = "text-embedding-3-small"

    # --- canonical Postgres (piano "Cervello DeliR", P0) ------------------
    # DSN come ruolo delir_app (solo DML, NOBYPASSRLS, non-owner). Usata dall'app.
    canonical_database_url: str | None = None
    # DSN come ruolo delir_migrator (owner dello schema). Usata solo da Alembic.
    canonical_migrator_url: str | None = None
    # DSN come ruolo delir_worker (drena solo le due code). Usata dai worker outbox.
    canonical_worker_url: str | None = None

    # --- Neo4j Community (projection grafo tipizzato, P0.5+) --------------
    neo4j_url: str = "bolt://127.0.0.1:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str | None = None

    langsmith_api_key: str | None = None
    langsmith_tracing: bool = False
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    langsmith_project: str = "BK-GPT"
    langsmith_provider: str = "openai"
    langsmith_model_name: str | None = None
    langsmith_tags: str = "delir"

    model_temperature: float = 1.0
    model_max_tokens: int = 4096
    model_timeout_seconds: int = 45
    model_max_retries: int = 1

    tavily_max_results: int = 5

    delir_auth_enabled: bool = False
    delir_api_token: str | None = None
    delir_admin_token: str | None = None
    delir_default_tenant_id: str = "local"
    delir_allowed_tenant_ids: str = ""
    delir_cors_origins: str = "http://127.0.0.1:3030,http://localhost:3030"

    prosimos_base_url: str = "http://127.0.0.1:5000"
    # Sync Prosimos runs the whole simulation inside the HTTP call, so this must
    # cover the slowest expected simulation, not just connect latency.
    prosimos_timeout_seconds: float = 900.0

    # --- simulation replay artifact (Phase 1) -------------------------------
    # KPIs are always computed from the full Prosimos event log; these bound the
    # *display* representation only (sampled token paths + time buckets).
    sim_replay_max_cases: int = 250
    sim_replay_buckets: int = 120
    sim_replay_schema_version: int = 1

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()


def truthy_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def langsmith_tracing_enabled() -> bool:
    return (
        settings.langsmith_tracing
        or truthy_env("LANGSMITH_TRACING")
        or truthy_env("LANGCHAIN_TRACING_V2")
    )


def effective_langsmith_model_name(model_name: str | None = None) -> str:
    return (settings.langsmith_model_name or model_name or settings.openai_model).strip()


def langsmith_metadata(model_name: str | None = None, **extra: str | None) -> dict[str, str]:
    metadata = {
        "ls_provider": settings.langsmith_provider.strip() or "openai",
        "ls_model_name": effective_langsmith_model_name(model_name),
    }
    metadata.update({key: value for key, value in extra.items() if value})
    return metadata


def langsmith_tags(*extra_tags: str | None) -> list[str]:
    tags: list[str] = []

    for tag in [
        *(settings.langsmith_tags.split(",") if settings.langsmith_tags else []),
        *extra_tags,
    ]:
        normalized = (tag or "").strip()
        if normalized and normalized not in tags:
            tags.append(normalized)

    return tags


def configure_langsmith_environment() -> None:
    if not langsmith_tracing_enabled():
        return

    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGCHAIN_TRACING_V2"] = "true"

    if settings.langsmith_api_key:
        os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
        os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key

    if settings.langsmith_endpoint:
        os.environ["LANGSMITH_ENDPOINT"] = settings.langsmith_endpoint
        os.environ["LANGCHAIN_ENDPOINT"] = settings.langsmith_endpoint

    if settings.langsmith_project:
        os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
        os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project


configure_langsmith_environment()

DEFAULT_OPENAI_MODEL = os.getenv("OPENAI_MODEL", settings.openai_model)

ALLOWED_MODELS = {
    "gpt-5.6-luna",
}

Path("data").mkdir(exist_ok=True)
