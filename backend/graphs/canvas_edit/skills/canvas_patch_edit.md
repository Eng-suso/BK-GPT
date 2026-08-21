---
name: canvas_patch_edit
description: Perform local deterministic BPMN edits without regenerating the process.
---

# Canvas Patch/Edit

Patch/Edit handles small scoped canvas changes.

## Allowed Work

- Rename or document an element.
- Add or remove one local element.
- Connect or reconnect a small number of sequence flows.
- Repair layout without changing semantics.

## Rules

- List elements first when ids are uncertain.
- Keep the change local.
- Validate after mutation when possible.
- Escalate to Construction when the request changes a significant process section.
