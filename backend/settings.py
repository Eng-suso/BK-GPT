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

    langsmith_api_key: str | None = None
    langsmith_tracing: bool = False
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    langsmith_project: str = "BK-GPT"

    model_temperature: float = 1.0
    model_max_tokens: int = 2048
    model_timeout_seconds: int = 60
    model_max_retries: int = 2

    tavily_max_results: int = 5

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()


def configure_langsmith_environment() -> None:
    if not settings.langsmith_tracing:
        return

    os.environ.setdefault("LANGSMITH_TRACING", "true")

    if settings.langsmith_api_key:
        os.environ.setdefault("LANGSMITH_API_KEY", settings.langsmith_api_key)

    if settings.langsmith_endpoint:
        os.environ.setdefault("LANGSMITH_ENDPOINT", settings.langsmith_endpoint)

    if settings.langsmith_project:
        os.environ.setdefault("LANGSMITH_PROJECT", settings.langsmith_project)


configure_langsmith_environment()

DEFAULT_OPENAI_MODEL = os.getenv("OPENAI_MODEL", settings.openai_model)

ALLOWED_MODELS = {
    "gpt-5.6-luna",
}

Path("data").mkdir(exist_ok=True)
