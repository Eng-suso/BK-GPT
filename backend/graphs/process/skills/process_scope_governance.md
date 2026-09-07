---
name: process_scope_governance
description: Define ownership boundaries between Process, Project, Consulting and Canvas scopes.
---

# Process Scope Governance

## Process Owns

- Single-process discovery and As-Is understanding.
- The process record: stage, status, owner and readiness (`update_workspace_process`). When the work moves, the record moves with it - an AS-IS the people who run it have confirmed is `Validato`, and saying so in prose while the record still reads `Bozza` leaves the next reader with the wrong process.
- Process evidence synthesis for one process.
- ProcessUnderstanding review and readiness.
- BPMNSemanticModel preparation.
- Handoff to Canvas Macro.

## Process Does Not Own

- Cross-process sequencing and dependencies across a project.
- Project phase, delivery status, risks and deliverables.
- Consulting strategy across clients or projects.
- Direct BPMN XML edits, final XML replacement or canvas layout.

## Routing Rules

Ask one focused clarification only when required ids or the target process are missing.
If the task touches several processes, route to Project Process Coordination.
If the task touches XML or canvas rendering, prepare a Canvas handoff.
