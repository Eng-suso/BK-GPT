"""Typed transport for a read-only process review and its separate action log."""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.process_understanding import ProcessUnderstanding

ReviewActionKind = Literal["candidate", "as_is_proposal", "clarification", "deferred"]


class CreateImpactReviewAction(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    id: UUID
    node_id: str = Field(min_length=1, max_length=256)
    base_revision: str = Field(min_length=64, max_length=64)
    kind: ReviewActionKind
    title: str = Field(min_length=1, max_length=180)
    detail: str = Field(min_length=1, max_length=4000)
    proposal_xml: str | None = Field(default=None, max_length=1_000_000)


class ImpactReviewAction(BaseModel):
    id: str
    node_id: str
    node_name: str
    base_revision: str
    kind: ReviewActionKind
    title: str
    detail: str
    created_at: str
    created_by: str
    proposal_xml: str | None = None


class ImpactReviewState(BaseModel):
    process_id: str
    base_revision: str
    xml: str | None
    plan: ProcessUnderstanding | None
    actions: list[ImpactReviewAction]
