from backend.settings import settings, SYSTEM_PROMPT, ALLOWED_MODELS, DEFAULT_GOOGLE_MODEL, DEFAULT_OPENAI_MODEL
from langchain_core.tools import tool #decorator
from langchain_tavily import TavilySearch
from backend.database import db
