from uuid import uuid4

from fastapi import FastAPI
from pydantic import BaseModel

from backend.agent import get_agent
from backend.memory.semantic.semantic_store import (
    save_consultant_memory,
    search_consultant_memory,
)

app = FastAPI()


class ChatRequest(BaseModel):
    model_name: str | None = None
    messages: list[dict]  # List of messages, each message is a dict with 'role' and 'content'
    thread_id: str


class CreateSessionRequest(BaseModel):
    model_name: str | None = None


class CreateSessionResponse(BaseModel):
    thread_id: str
    model_name: str | None = None


class SendMessageRequest(BaseModel):
    message: str
    model_name: str | None = None


class ChatResponse(BaseModel):
    thread_id: str
    message: str


class SaveMemoryRequest(BaseModel):
    content: str
    category: str


class SearchMemoryRequest(BaseModel):
    query: str
    category: str | None = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat")
def chat(request: ChatRequest) -> ChatResponse:
    agent = get_agent(request.model_name)

    result = agent.invoke(
        {
            "messages": request.messages
        },
        config={
            "configurable": {
                "thread_id": request.thread_id
            }
        },
    )

    messages = result.get("messages", [])
    last_message = messages[-1] if messages else None

    return ChatResponse(
        thread_id=request.thread_id,
        message=last_message.content if last_message else "",
    )


@app.post("/v1/consultant-chat/sessions")
def create_consultant_chat_session(request: CreateSessionRequest) -> CreateSessionResponse:
    return CreateSessionResponse(
        thread_id=str(uuid4()),
        model_name=request.model_name,
    )


@app.post("/v1/consultant-chat/sessions/{thread_id}/messages")
def send_consultant_chat_message(
    thread_id: str,
    request: SendMessageRequest,
) -> ChatResponse:
    agent = get_agent(request.model_name)

    result = agent.invoke(
        {
            "messages": [
                {"role": "user", "content": request.message},
            ]
        },
        config={
            "configurable": {
                "thread_id": thread_id,
            }
        },
    )

    messages = result.get("messages", [])
    last_message = messages[-1] if messages else None

    return ChatResponse(
        thread_id=thread_id,
        message=last_message.content if last_message else "",
    )


@app.post("/v1/memory/save")
def save_memory(request: SaveMemoryRequest):
    result = save_consultant_memory(
        content=request.content,
        category=request.category,
    )

    return {
        "result": result,
    }


@app.post("/v1/memory/search")
def search_memory(request: SearchMemoryRequest):
    result = search_consultant_memory(
        query=request.query,
        category=request.category,
    )

    return {
        "result": result,
    }
