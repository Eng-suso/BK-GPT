from fastapi import APIRouter, Depends

from backend.memory.semantic.semantic_store import save_consultant_memory, search_consultant_memory
from backend.schemas.chat_api import SaveMemoryRequest, SearchMemoryRequest
from backend.security import require_principal


router = APIRouter(prefix="/v1/memory", tags=["memory"], dependencies=[Depends(require_principal)])


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
