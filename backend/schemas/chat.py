from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, Field


class ConsultantChatScope(BaseModel):
    type: Literal["consultant"]


class ProjectChatScope(BaseModel):
    type: Literal["project"]
    project_id: str


class ProcessChatScope(BaseModel):
    type: Literal["process"]
    project_id: str
    process_id: str


class CanvasChatScope(BaseModel):
    type: Literal["canvas"]
    project_id: str
    process_id: str
    bpmn_model_id: str
    current_bpmn_xml: str | None = None


ChatScope: TypeAlias = Annotated[
    ConsultantChatScope | ProjectChatScope | ProcessChatScope | CanvasChatScope,
    Field(discriminator="type"),
]


def chat_scope_key(scope: ChatScope | None) -> str:
    if scope is None or scope.type == "consultant":
        return "consultant"
    if scope.type == "project":
        return f"project:{scope.project_id}"
    if scope.type == "process":
        return f"process:{scope.project_id}:{scope.process_id}"
    return f"canvas:{scope.project_id}:{scope.process_id}:{scope.bpmn_model_id}"
