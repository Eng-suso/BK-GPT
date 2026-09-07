---
name: project_delegation_policy
description: Decide Project Chat ownership and handoffs to subgraphs or macro agents.
---

# Project Delegation Policy

## Delegation Matrix

| User intent | Owner |
| --- | --- |
| Project-level synthesis, context, discussion | Project Macro |
| Add, create or register a process in this project | Project Macro (`create_project_process`) |
| Write the project record: objective, or correcting a stated field | Project Macro (`update_workspace_project`) |
| Save or retrieve project interview/evidence from Project Chat | Project Macro |
| Extract graph relationships/gaps/ROI from project evidence | Project Macro |
| Relation-heavy project retrieval, evidence links, project GraphRAG | Project Macro |
| Phase, progress, milestone, deliverable, risk, next step | Delivery subgraph |
| Several processes, sequencing, readiness matrix, dependencies | Process Coordination subgraph |
| One process AS-IS/TO-BE discovery or BPMN semantic review | Process Macro |
| BPMN XML, canvas edits, layout, versions, validation | Canvas Macro |

## Tool Budget

No Project macro agent or project subagent should expose more than 10 direct tools. The budget keeps the menu legible; it was 8 until the scope took back two capabilities it already owned on paper - registering a process, and writing the project record - because a capability the scope owns is worth more than a round number, and a tool the prompt names has to be a tool the agent has.

## Guardrails

- Do not let Project Macro do deep process work just because the user is in Project Chat.
- Do not send the full chat history as a handoff payload.
- Do not mutate project records through prepare-only tools. The Delivery subgraph plans and frames; the write is `update_workspace_project`, here. A plan the agent narrates and never records is a plan the workspace does not have.
- Never delegate to get a process created. Process Macro needs a `process_id`; handing it a name for a process nobody registered is a handoff into a dead end. Create the record here, then delegate the work on it.
- Registering a process ends the turn at the record. Discovery starts when the consultant asks for it, in Process Chat.
