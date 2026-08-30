---
name: canvas_construction
description: Build or rebuild BPMN canvas sections from semantic process models.
---

# Canvas Construction

Construction handles significant build or rebuild work.

## Rules

- Start from ProcessUnderstanding and BPMNSemanticModel when available.
- If the user supplies a raw process description and no semantic model exists yet, prepare a BPMN review from that description.
- Retrieve evidence/traceability context when available.
- Preserve unresolved gaps in the semantic payload, compilation plan and business report, not as visible canvas annotations.
- Keep the visible canvas focused on operational BPMN: lanes, events, activities, gateways and sequence flows.
- Do not render data objects, handoffs, business rules, unknowns, evidence or traceability as visible text annotations or association edges unless the user explicitly asks for that visual layer.
- Produce a preview before applying broad changes.
- Save only after validation and explicit approval.
