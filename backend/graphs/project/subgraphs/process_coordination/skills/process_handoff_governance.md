---
name: process_handoff_governance
description: Prepare narrow handoffs from Project Chat to Process Chat.
---

# Process Handoff Governance

## Handoff Payload

Include only:

- project_id
- process_id
- bpmn_model_id when known
- current blocker or objective
- relevant source or decision ids
- expected result
- reason for handoff

## Guardrail

Do not ask Process Macro to coordinate the entire project. Send one focused process objective at a time.
