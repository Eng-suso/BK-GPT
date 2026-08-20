---
name: workspace_triage
description: Decide how the Consult Macro Agent should interpret and route Home, Clients, and Projects workspace requests.
---

# Workspace Triage

## Purpose

Use this skill when the Consulting Chat needs to understand workspace state, update Home/Clients/Projects indirectly, or route an operational request to the correct owner.

## Workspace Areas

Home is for:

- global status
- priorities
- next actions
- active risks
- recent activity
- cross-project overview

Clients is for:

- client identity
- client status
- owner/contact metadata
- linked projects
- client-level notes

Projects is for:

- project phase and status
- progress
- next step
- sources
- decisions
- linked processes
- deliverables

## Operating Procedure

1. Identify the entity type: Home, Client, Project, Process, Canvas, or unknown.
2. Check whether the user is asking for strategy, read-only overview, or mutation.
3. For read-only overview, gather only the minimum workspace context needed.
4. For mutations, require a real operational intent such as create, add, update, register, archive, or set.
5. Route the mutation to the owner subagent instead of using low-level generic tools directly.
6. If the request names a project/process but lacks an id, list or search relevant workspace records before asking the user.

## Routing

- Home summary or priorities: Home subagent.
- New or updated client: Clients subagent.
- New or updated project: Project Macro Agent.
- Sources or decisions inside a project: Project Macro Agent.
- Process discovery/modeling: Process Macro Agent.
- BPMN canvas operations: Canvas Macro Agent.

## Guardrails

- Do not create duplicate clients or projects without checking existing records.
- Do not record vague brainstorming as workspace data.
- Do not cross from project work into process or canvas work unless the user intent clearly requires it.
