from fastapi import FastAPI
from pydantic import BaseModel
from backend.agent import get_agent

app = FastAPI()

class ChatRequest(BaseModel):
    model_name: str | None = None
    messages: list[dict]  # List of messages, each message is a dict with 'role' and 'content'
    thread_id: str | None = None  # Optional thread ID for conversation context

@app.post("/chat")
def chat(request: ChatRequest):
    agent = get_agent(request.model_name)

    result = agent.invoke(
        {
            "messages": [
                {"role": "user", "content": request.message}
            ]
        },
        config={
            "configurable": {
                "thread_id": request.thread_id
            }
        },
    )

    return result