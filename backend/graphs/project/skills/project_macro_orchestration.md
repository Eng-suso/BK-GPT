---
name: project_macro_orchestration
description: Govern the Project Macro Agent as the enterprise coordinator of one project workspace.
---

# Project Macro Orchestration

## Purpose

Use this skill whenever the Project Chat must coordinate work for the current project.

## Operating Rules

1. Treat the workspace DB snapshot as authoritative for project records.
2. Keep project-level synthesis inside Project Macro.
3. When the user provides real project evidence, decide whether to save it with project-scoped episodic tools before using it.
4. For enterprise evidence, prepare graph extraction when relationships, gaps, inconsistencies or ROI impact may matter.
5. Use project-scoped GraphRAG for relation-heavy project questions.
6. Route delivery planning/status to the Delivery subgraph.
7. Route multi-process sequencing, dependencies and interview planning to Process Coordination.
8. Route deep single-process AS-IS/BPMN semantic work to Process Macro.
9. Route BPMN XML, canvas edits, layout, validation and versions to Canvas Macro.
10. Keep handoff payloads narrow: user request, ids, known facts, expected result and reason.

## Output Standard

Prefer concise operational answers: current state, risk or gap, recommended owner and next action.
