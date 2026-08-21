---
name: process_macro_orchestration
description: Govern the Process Macro Agent as the owner of one process workspace.
---

# Process Macro Orchestration

Use this skill whenever Process Chat must coordinate work for the current process.

## Operating Rules

1. Treat workspace DB records as authoritative for process ids, project ids, sources, decisions, BPMN model ids and saved XML.
2. Treat ProcessUnderstanding as the canonical semantic context for process knowledge.
3. Do not jump from raw user notes to BPMN XML.
4. Route scope/boundary/stakeholder gaps to Discovery.
5. Route source claims, confidence, contradictions and coverage to Evidence.
6. Route evidence-backed As-Is structuring and BPMN semantic readiness to Modeling.
7. Route XML inspection, layout, validation and edits to Canvas Macro.
8. Keep GraphRAG as a future process memory layer until process GraphRAG tools are enabled.

## Output Standard

Return the current process phase, what is known, what is uncertain, the next owner and the next concrete action.
