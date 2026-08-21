---
name: canvas_construction
description: Build or rebuild BPMN canvas sections from semantic process models.
---

# Canvas Construction

Construction handles significant build or rebuild work.

## Rules

- Start from ProcessUnderstanding and BPMNSemanticModel.
- Retrieve evidence/traceability context when available.
- Preserve unresolved gaps as warnings or annotations.
- Produce a preview before applying broad changes.
- Save only after validation and explicit approval.
