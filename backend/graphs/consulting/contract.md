# Consulting Macro Branch Contract

## Status

Accepted for MVP iteration.

## Purpose

The Consulting Macro branch is the entry point for the Consulting Chat.

It coordinates consultant-level strategy, memory, workspace triage, Home, Clients, and initial setup.
It is not a universal agent and must delegate project execution, process work, and canvas work to their macro agents.

## Macro Owner

The Consult Macro Agent owns:

- consultant identity, method, positioning, offers, priorities, and working style
- semantic and episodic consultant memory
- external research when current external information is required
- cross-client and cross-project synthesis
- routing to Home, Clients, Setup, Project, Process, and Canvas owners

It does not own:

- project execution details
- process discovery or process modeling
- BPMN semantic review execution
- BPMN XML, canvas layout, validation, or versioning

## Direct Tool Budget

The Consult Macro Agent should stay below 8 direct tools.

If it needs more, add a subgraph, a tool facade, or a narrower macro agent.

## Current Direct Tools

- `get_workspace_overview`: read-only global workspace snapshot for strategic synthesis and routing.
- `prepare_delegation_payload`: structured handoff payload for another owner.
- `remember_consultant_fact`: save durable consultant-level facts.
- `search_consultant_memory`: retrieve durable consultant-level facts and preferences.
- `save_episode`: save dated source-backed context.
- `search_episodes`: search dated source-backed context.
- `web_research`: search current external information.

## Internal Subgraphs

### Home Subgraph

Owns dashboard-level synthesis: priorities, risks, next actions, and workspace overview.

Current tools:

- `get_workspace_overview`
- `prepare_home_dashboard_update`
- `record_home_priority`
- `record_home_risk`
- `record_next_action`

### Clients Subgraph

Owns client-level records from Consulting Chat: list clients, check duplicates, create explicit real clients.

Current tools:

- `get_workspace_overview`
- `list_workspace_clients`
- `manage_client_record`

### Setup Subgraph

Owns explicit initial workspace setup: client plus project, process stub, source, or decision.
After setup, ongoing execution moves to Project, Process, or Canvas macro agents.

Current tools:

- `get_workspace_overview`
- `validate_initial_workspace_setup`
- `create_initial_workspace_setup`

## External Delegation Targets

- Project Macro Agent: project execution, phase, progress, sources, decisions, next step, deliverables.
- Process Macro Agent: AS-IS/TO-BE discovery, evidence synthesis, readiness, semantic process model.
- Canvas Macro Agent: BPMN XML, live canvas inspection, deterministic edits, validation, layout, versions.

## Router Output

The Consulting router returns structured state:

- `consulting_route`
- `delegation_target`
- `delegation_reason`
- `routing_confidence`
- `needs_clarification`
- `clarification_question`
- `entity_hints`
- `delegation_payload`

## Routing Rules

The router must decide using intent and ownership, not keyword matching.

It should ask for clarification when the target owner or required entity is ambiguous.

It should include a narrow delegation payload containing only the latest user request, known hints, target owner, expected result, and reason.

## Procedural Memory

Always load local Consulting skills from `backend/graphs/consulting/skills`.

Subgraphs load only their own local skills from their `skills/` folder.

Do not load process or canvas procedural memory into the Consult Macro Agent unless the current task is only explaining routing.

## Guardrails

- Do not mutate workspace records during brainstorming.
- Do not create duplicate clients or projects without checking existing records.
- Do not use generic workspace tools in the Consult Macro Agent when a subgraph owns the operation.
- Do not present delegation as completed work unless a tool result confirms completion.
