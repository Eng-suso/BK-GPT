---
name: process_graph_memory_governance
description: Prepare process evidence for future GraphRAG without claiming retrieval or indexing before it exists.
---

# Process Graph Memory Governance

## Current Status

Process GraphRAG runs on the canonical Knowledge Graph: a Postgres store
(authoritative, RLS-scoped) projected to Neo4j through a transactional outbox.
Writes go through `mirror.mirror_evidence` -> `canonical.write_evidence`; reads
go through the scoped gateway (`backend.memory.gateway`). No tool queries Neo4j
or Postgres-KG directly.

## Entities

- process
- source
- claim
- actor
- activity
- decision
- handoff
- system
- document
- gap
- contradiction
- BPMN element

## Relations

- SOURCE_SUPPORTS_CLAIM
- CLAIM_DESCRIBES_ACTIVITY
- CLAIM_DESCRIBES_HANDOFF
- CLAIM_CONTRADICTS_CLAIM
- ACTIVITY_PERFORMED_BY_ACTOR
- ACTIVITY_USES_SYSTEM
- DECISION_SPLITS_PATH
- GAP_BLOCKS_MODELING
- PROCESS_ELEMENT_MAPS_TO_BPMN

## Rules

Use graph retrieval for relation-heavy process questions, not simple workspace lookup.
Keep source, claim, confidence, contradiction and element-hint fields in a graph-ready shape.
Use workspace DB as authoritative operational state.
