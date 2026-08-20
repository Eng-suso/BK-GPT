from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ConsultantSemanticMemory(BaseModel):
    memory_type: Literal["semantic"] = "semantic"
    category: str = Field(description="Stable consultant-level category, such as positioning or delivery_method.")
    entity_names: list[str] = Field(default_factory=list, description="Named entities Mem0 should link.")
    statement: str = Field(description="One durable fact, preference, rule, or stable pattern.")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="Confidence that this should affect future turns.")
    source: str = Field(default="chat", description="Where this memory came from.")
    durability: Literal["stable", "preference", "profile", "method", "working_assumption"] = "stable"

    @field_validator("category", "statement", "source")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        cleaned = " ".join(str(value or "").split())
        if not cleaned:
            raise ValueError("field cannot be empty")
        return cleaned

    @field_validator("entity_names")
    @classmethod
    def clean_entities(cls, values: list[str]) -> list[str]:
        cleaned = []
        for value in values:
            entity = " ".join(str(value or "").split())
            if entity and entity not in cleaned:
                cleaned.append(entity)
        return cleaned


class EpisodeMemory(BaseModel):
    memory_type: Literal["episodic"] = "episodic"
    episode_type: str = Field(description="Event type, such as call, note, decision, experiment, feedback, or interview.")
    title: str = Field(description="Short source-backed event title.")
    raw_content: str = Field(description="Original source text or notes. Stored locally as raw source custody.")
    summary: str = Field(default="", description="Concise extracted summary, not raw transcript replacement.")
    insights: list[str] = Field(default_factory=list, description="Extracted insights supported by raw_content.")
    participants: list[str] = Field(default_factory=list, description="People or roles involved.")
    project: str | None = Field(default=None, description="Related project name or id.")
    tags: list[str] = Field(default_factory=list, description="Retrieval tags.")
    occurred_at: str | None = Field(default=None, description="ISO date/time if known.")
    entity_names: list[str] = Field(default_factory=list, description="Named entities to include in Mem0 indexing.")

    @field_validator("episode_type", "title", "raw_content")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        cleaned = str(value or "").strip()
        if not cleaned:
            raise ValueError("field cannot be empty")
        return cleaned

    @field_validator("summary")
    @classmethod
    def strip_optional_text(cls, value: str) -> str:
        return str(value or "").strip()

    @field_validator("insights", "participants", "tags", "entity_names")
    @classmethod
    def clean_string_lists(cls, values: list[str]) -> list[str]:
        cleaned = []
        for value in values:
            item = " ".join(str(value or "").split())
            if item and item not in cleaned:
                cleaned.append(item)
        return cleaned


class ConsultingContextRetrievalRequest(BaseModel):
    query: str = Field(description="The retrieval question to answer.")
    retrieval_scope: Literal["semantic", "episodic", "interview", "both"] = Field(
        default="both",
        description="Which memory layer to retrieve from.",
    )
    category: str | None = Field(default=None, description="Optional semantic memory category.")
    episode_type: str | None = Field(default=None, description="Optional episodic event type.")
    project: str | None = Field(default=None, description="Optional project filter for episodic retrieval.")
    limit: int = Field(default=5, ge=1, le=10, description="Maximum local episodic matches.")
    reason: str = Field(description="Why this retrieval is needed for the current turn.")

    @field_validator("query", "reason")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        cleaned = " ".join(str(value or "").split())
        if not cleaned:
            raise ValueError("field cannot be empty")
        return cleaned


class ConsultingGraphRetrievalRequest(BaseModel):
    query: str = Field(description="Relation-heavy question to answer using consultant memory and entity links.")
    entities: list[str] = Field(
        default_factory=list,
        description="Named entities to anchor retrieval, such as Sohay, DeliR, a client, a project, an offer, a source, or a decision.",
    )
    relation_focus: str = Field(
        description=(
            "The relation type to inspect, for example client-to-project, project-to-source, "
            "offer-to-ICP, decision-to-risk, insight-to-evidence, or preference-to-delivery."
        )
    )
    reason: str = Field(description="Why graph-style relational retrieval is needed now.")
    include_workspace_overview: bool = Field(
        default=True,
        description="Include current workspace DB overview as grounding. Recommended for client/project/process relations.",
    )
    limit: int = Field(default=5, ge=1, le=10, description="Maximum local episodic matches.")

    @field_validator("query", "relation_focus", "reason")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        cleaned = " ".join(str(value or "").split())
        if not cleaned:
            raise ValueError("field cannot be empty")
        return cleaned

    @field_validator("entities")
    @classmethod
    def clean_entities(cls, values: list[str]) -> list[str]:
        cleaned = []
        for value in values:
            entity = " ".join(str(value or "").split())
            if entity and entity not in cleaned:
                cleaned.append(entity)
        return cleaned


def semantic_memory_to_mem0_content(memory: ConsultantSemanticMemory) -> str:
    return "\n".join(
        [
            f"memory_type: {memory.memory_type}",
            f"category: {memory.category}",
            f"durability: {memory.durability}",
            f"confidence: {memory.confidence}",
            f"source: {memory.source}",
            f"entities: {', '.join(memory.entity_names) or 'none'}",
            f"statement: {memory.statement}",
        ]
    )


def episode_memory_to_mem0_content(memory: EpisodeMemory, episode_id: str, source_id: str, source_path: str) -> str:
    return "\n".join(
        [
            f"memory_type: {memory.memory_type}",
            f"episode_id: {episode_id}",
            f"source_id: {source_id}",
            f"type: {memory.episode_type}",
            f"title: {memory.title}",
            f"occurred_at: {memory.occurred_at or 'unknown'}",
            f"participants: {', '.join(memory.participants) or 'unknown'}",
            f"project: {memory.project or 'none'}",
            f"tags: {', '.join(memory.tags) or 'none'}",
            f"entities: {', '.join(memory.entity_names) or 'none'}",
            f"summary: {memory.summary or 'none'}",
            f"insights: {' | '.join(memory.insights) or 'none'}",
            f"source_path: {source_path}",
        ]
    )
