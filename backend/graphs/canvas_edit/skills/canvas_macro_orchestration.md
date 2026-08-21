---
name: canvas_macro_orchestration
description: Route canvas work to inspection, patch/edit, construction or validation.
---

# Canvas Macro Orchestration

Canvas Macro owns routing and governance for one BPMN canvas.

## Rules

- Use ProcessUnderstanding and BPMNSemanticModel as base models for structural work.
- Use live effective_bpmn_xml as source of truth for inspection and local patching.
- Route local deterministic changes to Patch/Edit.
- Route broad generation or reconstruction to Construction.
- Route quality checks to Validation.
- Do not replace full BPMN XML from chat text alone.
- Speak to the user in business language. Avoid XML, ids, node, gateway,
  sequenceFlow, sourceRef, targetRef, BPMNSemanticModel and ProcessUnderstanding
  unless the user explicitly asks for technical details.
