---
name: process_graph_memory_governance
description: Prepare process evidence for future GraphRAG without claiming retrieval or indexing before it exists.
---

# Process Graph Memory Governance

## Current Status

Process GraphRAG is enabled through the enterprise Knowledge Graph facade.
The current backend is local and replaceable; LlamaIndex should sit behind the
same facade when the RAG backend is added.

## Future Entities

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

## Future Relations

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
