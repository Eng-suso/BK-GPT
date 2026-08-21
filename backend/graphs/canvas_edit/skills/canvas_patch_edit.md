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
- Use the exact listed BPMN id; do not do fuzzy/token search.
- Use `clear_canvas` when the user asks to remove all visible canvas elements.
- Do not ask for confirmation after an explicit delete request unless the listed model is missing or ambiguous.
- Keep the change local.
- Validate after mutation when possible.
- Escalate to Construction when the request changes a significant process section.
