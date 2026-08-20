from fastapi import APIRouter

from backend.memory.semantic.semantic_store import save_consultant_memory, search_consultant_memory
from backend.schemas.chat_api import SaveMemoryRequest, SearchMemoryRequest


router = APIRouter(prefix="/v1/memory", tags=["memory"])


@router.post("/save")
def save_memory(request: SaveMemoryRequest):
    result = save_consultant_memory(
        content=request.content,
        category=request.category,
    )

    return {
        "result": result,
    }


@router.post("/search")
def search_memory(request: SearchMemoryRequest):
    result = search_consultant_memory(
        query=request.query,
        category=request.category,
    )

    return {
        "result": result,
    }
