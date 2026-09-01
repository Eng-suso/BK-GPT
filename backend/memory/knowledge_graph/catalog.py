"""Catalogo canonico Postgres -> projection Neo4j (P0.5).

Sorgente di verita' della struttura del grafo L1. Il projector (P1) legge
questo modulo per sapere:
  - quali tabelle Postgres diventano nodi e quali archi;
  - quali colonne finiscono in Neo4j (whitelist) e quali restano solo in
    Postgres (INV-5 / B+);
  - quali archi strutturali derivare da FK e colonne array.

Nessun codice di proiezione qui: solo la mappa dichiarativa + un lint.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --- INV-5: campi che non devono MAI raggiungere Neo4j -------------------
# `name` generico NON e' qui: i nomi di processo/progetto sono etichette di
# business, non dati personali. E' il `canonical_name` di kg_entity (nome di
# persona) a essere vietato.
PII_FORBIDDEN_IN_NEO4J: frozenset[str] = frozenset(
    {
        "canonical_name",
        "aliases",
        "email",
        "phone",
        "employee_id",
        "username",
        "address",
        "statement",          # testo del claim: puo' contenere dettagli sensibili
        "evidence",
        "mechanism",
        "missing_information",
        "resolution",
        "resolution_question",
        "conflicting_statements",
        "raw_content",
        "embedding",
        "attributes",          # l'intero blob: solo le chiavi whitelisted passano
    }
)

# attributi semantici non identificativi ammessi da kg_entity.attributes
ENTITY_ATTR_WHITELIST: frozenset[str] = frozenset(
    {"role_type", "department_type", "seniority", "actor_type", "function_type"}
)

# scope keys presenti su ogni nodo/arco per l'enforcement del gateway (INV-9)
SCOPE_PROPS: tuple[str, ...] = ("client_id", "project_id", "layer")


@dataclass(frozen=True)
class NodeSpec:
    table: str
    label: str
    id_prop: str                      # nome della proprieta' id in Neo4j
    props: tuple[str, ...]            # colonne scalari proiettate as-is
    attr_whitelist: frozenset[str] = frozenset()  # chiavi estratte da `attributes`
    pg_only: tuple[str, ...] = ()     # documentazione: colonne che restano in PG

    def neo4j_props(self) -> tuple[str, ...]:
        return (self.id_prop, *SCOPE_PROPS, "status", "confidence", *self.props)


@dataclass(frozen=True)
class EdgeSpec:
    table: str
    label_column: str                 # il tipo dell'arco = valore di questa colonna
    source: tuple[str, str]           # (tabella entita', colonna FK)
    target: tuple[str, str]
    props: tuple[str, ...] = ()
    pg_only: tuple[str, ...] = ()


@dataclass(frozen=True)
class StructuralEdge:
    """Arco derivato da una FK o da una colonna array, tipo fisso."""

    from_table: str
    label: str
    from_node: str                    # label del nodo sorgente
    to_node: str                      # label del nodo target
    via: str                          # colonna: scalare -> 1 arco, array -> N archi
    array: bool = False


NODES: tuple[NodeSpec, ...] = (
    NodeSpec(
        table="process",
        label="Process",
        id_prop="process_id",
        props=("name",),              # nome di processo = etichetta di business, non PII
        pg_only=("created_at",),
    ),
    NodeSpec(
        table="kg_entity",
        label="Entity",
        id_prop="entity_id",
        props=("entity_type",),
        attr_whitelist=ENTITY_ATTR_WHITELIST,
        pg_only=("canonical_name", "aliases", "attributes", "embedding", "source_ids"),
    ),
    NodeSpec(
        table="kg_claim",
        label="Claim",
        id_prop="claim_id",
        props=("process_area", "claim_status", "linked_element_hint"),
        pg_only=("statement", "source_ids"),
    ),
    NodeSpec(
        table="kg_gap",
        label="Gap",
        id_prop="gap_id",
        props=("severity",),
        pg_only=("title", "missing_information", "required_evidence", "source_ids"),
    ),
    NodeSpec(
        table="kg_contradiction",
        label="Contradiction",
        id_prop="contradiction_id",
        props=("severity",),
        pg_only=(
            "title",
            "conflicting_statements",
            "resolution_question",
            "resolution",
            "source_ids",
        ),
    ),
    NodeSpec(
        table="kg_impact",
        label="Impact",
        id_prop="impact_id",
        props=("impact_area",),
        pg_only=("title", "mechanism", "evidence", "source_ids"),
    ),
)

EDGES: tuple[EdgeSpec, ...] = (
    EdgeSpec(
        table="kg_relation",
        label_column="relation",
        source=("kg_entity", "source_entity_id"),
        target=("kg_entity", "target_entity_id"),
        props=("relation_id", "confidence", "confirmed", *SCOPE_PROPS, "status"),
        pg_only=("evidence", "source_ids"),
    ),
)

STRUCTURAL_EDGES: tuple[StructuralEdge, ...] = (
    StructuralEdge("kg_claim", "HAS_CLAIM", "Process", "Claim", via="process_id"),
    StructuralEdge("kg_gap", "BLOCKS", "Gap", "Process", via="affected_process_ids", array=True),
    StructuralEdge("kg_contradiction", "AFFECTS", "Contradiction", "Process", via="affected_process_ids", array=True),
    StructuralEdge("kg_contradiction", "BETWEEN", "Contradiction", "Claim", via="conflicting_claim_ids", array=True),
    StructuralEdge("kg_impact", "AFFECTS", "Impact", "Process", via="affected_process_ids", array=True),
)

NODE_BY_TABLE: dict[str, NodeSpec] = {n.table: n for n in NODES}

# aggregate_type di graph_outbox -> gestore (INV-7); l'ordine e' quello di apply
OUTBOX_AGGREGATE_TYPES: tuple[str, ...] = (
    "entity",
    "process",
    "claim",
    "gap",
    "contradiction",
    "impact",
    "relation",
)


def assert_projectable(props: dict[str, object], *, context: str = "") -> None:
    """Lint per il projector: solleva se una prop vietata sta per finire in Neo4j."""
    leaked = PII_FORBIDDEN_IN_NEO4J & set(props)
    if leaked:
        raise ValueError(
            f"projection blocca {sorted(leaked)} verso Neo4j (INV-5 / B+)"
            + (f" — {context}" if context else "")
        )
