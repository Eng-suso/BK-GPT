import os
from pathlib import Path

import certifi

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict 



class Settings(BaseSettings):
    google_api_key: str
    google_model: str = "gemini-3.5-flash-light"

    tavily_api_key: str | None = None

    langsmith_api_key: str | None = None
    langsmith_tracing: bool = False
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    langsmith_project: str = "BK-GPT"

    model_temperature: float = 1.0
    model_max_tokens: int = 2048
    model_timeout_seconds: int = 60
    model_max_retries: int = 2
    model_thinking_level: str = "low"

    tavily_max_results: int = 5

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()

DEFAULT_GOOGLE_MODEL = os.getenv("GOOGLE_MODEL", settings.google_model) 
DEFAULT_OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")

ALLOWED_MODELS = {
    "gemini-2.5-flash",
    "gemini-3.1-pro",
    "gemini-3.5-flash-lite", # Included the lite version if needed
    "gpt-4.1-mini",
    "gpt-5.6-luna"
}
Path('data').mkdir(exist_ok=True)


# Step 1 — Install the SDK (run in your terminal, not in Python):
#pip install mem0ai

# Step 2 — Save this as mem0_quickstart.py and run with: python mem0_quickstart.py
import os
from mem0 import MemoryClient

# Set your API key (get one at https://app.mem0.ai)
client = MemoryClient(api_key=os.getenv("MEM0_API_KEY", "your-api-key-here"))

# Add a memory
messages = [
    {"role": "user", "content": "I'm a vegetarian and allergic to nuts."},
    {"role": "assistant", "content": "Got it! I'll remember your dietary preferences."},
]
client.add(messages, user_id="user123")

# Search memories
results = client.search(
    "What are my dietary restrictions?",
    user_id="user123",
)
print(results)