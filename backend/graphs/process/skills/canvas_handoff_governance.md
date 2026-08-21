---
name: canvas_handoff_governance
description: Prepare narrow handoffs from Process Macro to Canvas Macro.
---

# Canvas Handoff Governance

Canvas Macro receives canvas work only after Process Macro has checked the
semantic process context.

## Required Handoff Fields

- project_id
- process_id
- bpmn_model_id
- process name
- requested canvas action
- readiness score
- ProcessUnderstanding availability
- BPMNSemanticModel availability
- unresolved gaps
- constraints

## Rules

Do not ask Canvas Macro to discover the process.
Do not ask Canvas Macro to infer missing semantics from raw notes.
If readiness is weak, hand off only inspection or validation, not generation.
