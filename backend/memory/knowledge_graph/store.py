from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

from llama_index.core import Document, StorageContext, VectorStoreIndex, load_index_from_storage
from llama_index.core.embeddings import MockEmbedding
from llama_index.core.graph_stores import SimplePropertyGraphStore
from llama_index.core.graph_stores.types import EntityNode, Relation
from llama_index.embeddings.openai import OpenAIEmbedding

from backend.memory.knowledge_graph.models import (
    KnowledgeGraphContext,
    KnowledgeGraphEvidence,
    KnowledgeGraphQuery,
)
from backend.settings import settings


DATA_DIR = Path("data") / "knowledge_graph"
PROPERTY_GRAPH_PATH = DATA_DIR / "property_graph.json"
VECTOR_INDEX_DIR = DATA_DIR / "vector_index"
VECTOR_INDEX_ID = "enterprise_knowledge_graph_vector"


def clean_text(value: str | None) -> str:
    return " ".join(str(value or "").split())


def clean_list(values: list[str] | None) -> list[str]:
    cleaned = []
    for value in values or []:
        item = clean_text(value)
        if item and item not in cleaned:
            cleaned.append(item)
    return cleaned


def safe_node_id(prefix: str, value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_:-]+", "_", clean_text(value)).strip("_")
    return f"{prefix}:{clean or 'unknown'}"


def short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def force_mock_embeddings() -> bool:
    return os.getenv("DELIR_FORCE_MOCK_EMBEDDINGS", "").casefold() in {"1", "true", "yes"}


def relation_labels(payload: KnowledgeGraphEvidence) -> list[str]:
    labels = []
    for relationship in payload.relationships:
        label = clean_text(relationship.relation)
        if label and label not in labels:
            labels.append(label)
    return labels


def evidence_search_text(payload: KnowledgeGraphEvidence) -> str:
    parts = [
        "ENTERPRISE_KNOWLEDGE_GRAPH_EVIDENCE",
        f"project_id: {payload.project_id}",
        f"scope: {payload.scope}",
        f"source_title: {payload.source_title}",
        f"reason: {payload.reason}",
        payload.raw_content,
        f"process_ids: {', '.join(payload.process_ids)}",
        f"entities: {', '.join(payload.entities)}",
    ]
    for claim in payload.claims:
        parts.append(
            "claim: "
            f"{claim.claim} | area={claim.process_area} | source={claim.source_name} | "
            f"confidence={claim.confidence} | status={claim.status} | "
            f"linked_element={claim.linked_element_hint or 'none'}"
        )
    for relationship in payload.relationships:
        parts.append(
            "relationship: "
            f"{relationship.source} {relationship.relation} {relationship.target} | "
            f"confirmed={str(relationship.confirmed).lower()} | confidence={relationship.confidence} | "
            f"evidence={relationship.evidence} | source_ref={relationship.source_ref or 'none'}"
        )
    for gap in payload.gaps:
        parts.append(
            "gap: "
            f"{gap.title} | affected_process_ids={', '.join(gap.affected_process_ids) or 'unknown'} | "
            f"severity={gap.severity} | missing={gap.missing_information} | "
            f"required_evidence={gap.required_evidence or 'unspecified'}"
        )
    for contradiction in payload.contradictions:
        parts.append(
            "contradiction: "
            f"{contradiction.title} | affected_process_ids={', '.join(contradiction.affected_process_ids) or 'unknown'} | "
            f"severity={contradiction.severity} | claims={' || '.join(contradiction.conflicting_claims)} | "
            f"resolution_question={contradiction.resolution_question}"
        )
    for impact in payload.impacts:
        parts.append(
            "impact: "
            f"{impact.title} | area={impact.impact_area} | "
            f"affected_process_ids={', '.join(impact.affected_process_ids) or 'unknown'} | "
            f"confidence={impact.confidence} | mechanism={impact.mechanism} | evidence={impact.evidence or 'unspecified'}"
        )
    return "\n".join(clean_text(part) for part in parts if clean_text(part))


def query_terms(query: KnowledgeGraphQuery) -> list[str]:
    raw = " ".join(
        [
            query.query,
            query.relation_focus,
            " ".join(query.entities),
            " ".join(query.process_ids),
        ]
    )
    return [term for term in re.findall(r"[a-zA-Z0-9_:-]+", raw.casefold()) if len(term) > 2]


def relation_matches_focus(label: str, relation_focus: str) -> bool:
    normalized_label = clean_text(label).casefold()
    normalized_focus = clean_text(relation_focus).casefold().replace("_", "-")
    if normalized_label in normalized_focus:
        return True
    if normalized_focus in normalized_label.replace("_", "-"):
        return True
    if "claim" in normalized_focus and "activity" in normalized_focus:
        return normalized_label in {
            "claim_supports_activity",
            "claim_supports_process_element",
        }
    if "canvas" in normalized_focus and "traceability" in normalized_focus:
        return "canvas" in normalized_label or "process_element" in normalized_label
    if "contradiction" in normalized_focus:
        return "contradiction" in normalized_label
    return False


def process_ids_from_text(value: str, process_ids: list[str]) -> set[str]:
    haystack = clean_text(value)
    return {process_id for process_id in process_ids if process_id in haystack}


class KnowledgeGraphStore:
    backend_name = "llamaindex_property_graph_and_vector_index"

    def __init__(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        VECTOR_INDEX_DIR.mkdir(parents=True, exist_ok=True)

    def index_evidence_graph(self, payload: KnowledgeGraphEvidence) -> dict:
        normalized = payload.model_copy(
            update={
                "process_ids": clean_list(payload.process_ids),
                "entities": clean_list(payload.entities),
                "source_refs": clean_list(payload.source_refs),
            }
        )
        text = evidence_search_text(normalized)
        record_id = f"kg:{short_hash(text)}"
        graph_store = self._load_property_graph()
        graph_nodes, graph_relations = self._payload_to_graph(normalized, record_id)
        graph_store.upsert_nodes(graph_nodes)
        graph_store.upsert_relations(graph_relations)
        self._persist_property_graph(graph_store)
        self._insert_vector_document(normalized, record_id, text)

        return {
            "record_id": record_id,
            "project_id": normalized.project_id,
            "scope": normalized.scope,
            "process_ids": normalized.process_ids,
            "entities": normalized.entities,
            "relation_labels": relation_labels(normalized),
            "backend": self.backend_name,
            "property_graph_path": str(PROPERTY_GRAPH_PATH),
            "vector_index_dir": str(VECTOR_INDEX_DIR),
        }

    def retrieve_graph_context(self, query: KnowledgeGraphQuery) -> KnowledgeGraphContext:
        graph_store = self._load_property_graph()
        graph_matches = self._retrieve_property_graph(graph_store, query)
        vector_matches = self._retrieve_vector_context(query)
        matches = [*graph_matches, *vector_matches]
        matches = sorted(matches, key=lambda item: item.get("score", 0), reverse=True)[: query.limit]

        return KnowledgeGraphContext(
            status="ok" if matches else "empty",
            backend=self.backend_name,
            project_id=query.project_id,
            query=query.query,
            relation_focus=query.relation_focus,
            matches=matches,
        )

    def _embed_model(self):
        if force_mock_embeddings():
            return MockEmbedding(embed_dim=384)
        if settings.openai_api_key:
            return OpenAIEmbedding(api_key=settings.openai_api_key)
        return MockEmbedding(embed_dim=384)

    def _load_property_graph(self) -> SimplePropertyGraphStore:
        if PROPERTY_GRAPH_PATH.exists():
            return SimplePropertyGraphStore.from_persist_path(str(PROPERTY_GRAPH_PATH))
        return SimplePropertyGraphStore()

    def _persist_property_graph(self, graph_store: SimplePropertyGraphStore) -> None:
        PROPERTY_GRAPH_PATH.parent.mkdir(parents=True, exist_ok=True)
        graph_store.persist(str(PROPERTY_GRAPH_PATH))

    def _load_vector_index(self) -> VectorStoreIndex | None:
        if not (VECTOR_INDEX_DIR / "docstore.json").exists():
            return None

        storage_context = StorageContext.from_defaults(persist_dir=str(VECTOR_INDEX_DIR))
        index = load_index_from_storage(
            storage_context,
            index_id=VECTOR_INDEX_ID,
            embed_model=self._embed_model(),
        )
        return index

    def _create_vector_index(self, document: Document) -> VectorStoreIndex:
        index = VectorStoreIndex.from_documents(
            [document],
            embed_model=self._embed_model(),
        )
        index.set_index_id(VECTOR_INDEX_ID)
        index.storage_context.persist(persist_dir=str(VECTOR_INDEX_DIR))
        return index

    def _insert_vector_document(self, payload: KnowledgeGraphEvidence, record_id: str, text: str) -> None:
        if force_mock_embeddings():
            return

        document = Document(
            text=text,
            id_=record_id,
            metadata={
                "record_id": record_id,
                "project_id": payload.project_id,
                "scope": payload.scope,
                "source_title": payload.source_title,
                "process_ids": ",".join(payload.process_ids),
                "entities": ",".join(payload.entities),
                "relation_labels": ",".join(relation_labels(payload)),
            },
        )
        index = self._load_vector_index()
        if index is None:
            self._create_vector_index(document)
            return

        index.insert(document)
        index.storage_context.persist(persist_dir=str(VECTOR_INDEX_DIR))

    def _payload_to_graph(
        self,
        payload: KnowledgeGraphEvidence,
        record_id: str,
    ) -> tuple[list[EntityNode], list[Relation]]:
        nodes_by_id: dict[str, EntityNode] = {}
        relations: list[Relation] = []

        def add_node(node_id: str, label: str, **properties) -> str:
            merged_properties = {
                "project_id": payload.project_id,
                "record_id": record_id,
                **{key: value for key, value in properties.items() if value is not None},
            }
            nodes_by_id[node_id] = EntityNode(name=node_id, label=label, properties=merged_properties)
            return node_id

        def add_relation(source_id: str, label: str, target_id: str, **properties) -> None:
            relations.append(
                Relation(
                    label=label,
                    source_id=source_id,
                    target_id=target_id,
                    properties={
                        "project_id": payload.project_id,
                        "record_id": record_id,
                        **{key: value for key, value in properties.items() if value is not None},
                    },
                )
            )

        project_node = add_node(safe_node_id("project", payload.project_id), "Project")
        source_node = add_node(
            safe_node_id("source", payload.source_title),
            "Source",
            source_title=payload.source_title,
            source_refs=",".join(payload.source_refs),
            reason=payload.reason,
        )
        add_relation(project_node, "PROJECT_HAS_SOURCE", source_node)

        process_nodes = []
        for process_id in payload.process_ids:
            process_node = add_node(safe_node_id("process", process_id), "Process", process_id=process_id)
            process_nodes.append(process_node)
            add_relation(project_node, "PROJECT_HAS_PROCESS", process_node, process_id=process_id)
            add_relation(process_node, "PROCESS_HAS_SOURCE", source_node, process_id=process_id)

        for entity in payload.entities:
            entity_node = add_node(safe_node_id("entity", entity), "Entity", entity=entity)
            add_relation(project_node, "PROJECT_MENTIONS_ENTITY", entity_node)

        for claim in payload.claims:
            claim_node = add_node(
                safe_node_id("claim", short_hash(claim.claim)),
                "Claim",
                claim=claim.claim,
                process_area=claim.process_area,
                confidence=claim.confidence,
                status=claim.status,
                linked_element_hint=claim.linked_element_hint,
            )
            add_relation(source_node, "SOURCE_STATES_CLAIM", claim_node, evidence=claim.claim)
            for process_node in process_nodes:
                add_relation(process_node, "PROCESS_HAS_CLAIM", claim_node)
            if claim.linked_element_hint:
                element_node = add_node(
                    safe_node_id("process_element", claim.linked_element_hint),
                    "ProcessElement",
                    element_hint=claim.linked_element_hint,
                )
                add_relation(claim_node, "CLAIM_SUPPORTS_PROCESS_ELEMENT", element_node)

        for relationship in payload.relationships:
            source_id = add_node(relationship.source, "Entity")
            target_id = add_node(relationship.target, "Entity")
            add_relation(
                source_id,
                relationship.relation,
                target_id,
                evidence=relationship.evidence,
                confidence=relationship.confidence,
                confirmed=relationship.confirmed,
                source_ref=relationship.source_ref,
                process_ids=",".join(payload.process_ids),
            )

        for gap in payload.gaps:
            gap_node = add_node(
                safe_node_id("gap", short_hash(gap.title + gap.missing_information)),
                "Gap",
                title=gap.title,
                missing_information=gap.missing_information,
                required_evidence=gap.required_evidence,
                severity=gap.severity,
            )
            for process_id in gap.affected_process_ids or payload.process_ids:
                process_node = add_node(safe_node_id("process", process_id), "Process", process_id=process_id)
                add_relation(gap_node, "GAP_BLOCKS_MODELING", process_node, process_id=process_id)

        for contradiction in payload.contradictions:
            contradiction_node = add_node(
                safe_node_id("contradiction", short_hash(contradiction.title)),
                "Contradiction",
                title=contradiction.title,
                conflicting_claims=" || ".join(contradiction.conflicting_claims),
                resolution_question=contradiction.resolution_question,
                severity=contradiction.severity,
            )
            for process_id in contradiction.affected_process_ids or payload.process_ids:
                process_node = add_node(safe_node_id("process", process_id), "Process", process_id=process_id)
                add_relation(contradiction_node, "CONTRADICTION_AFFECTS_PROCESS", process_node, process_id=process_id)

        for impact in payload.impacts:
            impact_node = add_node(
                safe_node_id("impact", short_hash(impact.title + impact.mechanism)),
                "Impact",
                title=impact.title,
                impact_area=impact.impact_area,
                mechanism=impact.mechanism,
                evidence=impact.evidence,
                confidence=impact.confidence,
            )
            for process_id in impact.affected_process_ids or payload.process_ids:
                process_node = add_node(safe_node_id("process", process_id), "Process", process_id=process_id)
                add_relation(impact_node, "IMPACT_AFFECTS_PROCESS", process_node, process_id=process_id)

        return list(nodes_by_id.values()), relations

    def _retrieve_property_graph(
        self,
        graph_store: SimplePropertyGraphStore,
        query: KnowledgeGraphQuery,
    ) -> list[dict]:
        graph = graph_store.to_dict()
        nodes = graph.get("nodes") or {}
        relations = graph.get("relations") or {}
        terms = query_terms(query)
        matches = []
        record_process_ids: dict[str, set[str]] = {}

        for relation in relations.values():
            relation_props = relation.get("properties") or {}
            record_id = clean_text(relation_props.get("record_id"))
            if not record_id or relation_props.get("project_id") != query.project_id:
                continue

            source = nodes.get(relation.get("source_id"), {})
            target = nodes.get(relation.get("target_id"), {})
            source_props = source.get("properties") or {}
            target_props = target.get("properties") or {}
            process_haystack = " ".join(
                [
                    clean_text(relation_props.get("process_id")),
                    clean_text(relation_props.get("process_ids")),
                    clean_text(source_props.get("process_id")),
                    clean_text(target_props.get("process_id")),
                    clean_text(source_props.get("affected_process_ids")),
                    clean_text(target_props.get("affected_process_ids")),
                    relation.get("source_id") or "",
                    relation.get("target_id") or "",
                ]
            )
            linked_process_ids = process_ids_from_text(process_haystack, query.process_ids)
            if linked_process_ids:
                record_process_ids.setdefault(record_id, set()).update(linked_process_ids)

        for relation_key, relation in relations.items():
            source = nodes.get(relation.get("source_id"), {})
            target = nodes.get(relation.get("target_id"), {})
            relation_props = relation.get("properties") or {}
            source_props = source.get("properties") or {}
            target_props = target.get("properties") or {}

            if relation_props.get("project_id") != query.project_id:
                continue

            process_haystack = " ".join(
                [
                    clean_text(relation_props.get("process_id")),
                    clean_text(relation_props.get("process_ids")),
                    clean_text(source_props.get("process_id")),
                    clean_text(target_props.get("process_id")),
                    clean_text(source_props.get("affected_process_ids")),
                    clean_text(target_props.get("affected_process_ids")),
                    " ".join(record_process_ids.get(clean_text(relation_props.get("record_id")), set())),
                    relation.get("source_id") or "",
                    relation.get("target_id") or "",
                ]
            )
            if query.process_ids and not any(process_id in process_haystack for process_id in query.process_ids):
                continue

            haystack = " ".join(
                [
                    relation_key,
                    relation.get("label") or "",
                    relation.get("source_id") or "",
                    relation.get("target_id") or "",
                    " ".join(str(value) for value in relation_props.values()),
                    " ".join(str(value) for value in source_props.values()),
                    " ".join(str(value) for value in target_props.values()),
                ]
            ).casefold()
            score = sum(1 for term in terms if term in haystack)
            if relation_matches_focus(relation.get("label", ""), query.relation_focus):
                score += 20
            for entity in query.entities:
                if entity.casefold() in haystack:
                    score += 3
            if score <= 0 and query.query.strip():
                continue

            matches.append(
                {
                    "source": "llamaindex_property_graph",
                    "score": score,
                    "relation_key": relation_key,
                    "triplet": {
                        "source": relation.get("source_id"),
                        "relation": relation.get("label"),
                        "target": relation.get("target_id"),
                    },
                    "relation_properties": relation_props,
                    "source_node": source,
                    "target_node": target,
                }
            )

        return sorted(matches, key=lambda item: item["score"], reverse=True)[: query.limit]

    def _retrieve_vector_context(self, query: KnowledgeGraphQuery) -> list[dict]:
        if force_mock_embeddings():
            return []

        index = self._load_vector_index()
        if index is None:
            return []

        retriever = index.as_retriever(similarity_top_k=query.limit)
        vector_query = "\n".join(
            [
                f"project_id: {query.project_id}",
                f"process_ids: {', '.join(query.process_ids)}",
                f"relation_focus: {query.relation_focus}",
                f"entities: {', '.join(query.entities)}",
                f"query: {query.query}",
            ]
        )
        try:
            results = retriever.retrieve(vector_query)
        except Exception:
            return []

        matches = []
        for result in results:
            node = result.node
            metadata = dict(getattr(node, "metadata", {}) or {})
            if metadata.get("project_id") != query.project_id:
                continue
            metadata_process_ids = [
                item for item in str(metadata.get("process_ids") or "").split(",") if item
            ]
            if query.process_ids and not any(process_id in metadata_process_ids for process_id in query.process_ids):
                continue
            matches.append(
                {
                    "source": "llamaindex_vector_index",
                    "score": float(getattr(result, "score", 0.0) or 0.0),
                    "metadata": metadata,
                    "text": node.get_content(),
                }
            )
        return matches


knowledge_graph_store = KnowledgeGraphStore()
