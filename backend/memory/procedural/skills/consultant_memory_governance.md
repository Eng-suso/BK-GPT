---
name: consultant_memory_governance
description: Decide how consultant knowledge should be stored, retrieved, updated, and trusted. Use when a task involves semantic memory, episodic memory, procedural memory, durable preferences, profile facts, source-backed events, or memory hygiene.
---

# Consultant Memory Governance

## Purpose

Use this skill to decide how consultant knowledge should be stored, retrieved, updated, and trusted.

## Memory Types

Semantic memory stores durable facts and stable patterns:

- consultant identity
- positioning
- offers
- target clients
- recurring preferences
- delivery style
- stable constraints
- confirmed operating principles

Episodic memory stores dated, source-backed events:

- interviews
- calls
- meeting notes
- decisions
- experiments
- feedback
- observations
- source material

Procedural memory stores reusable ways of working:

- discovery method
- modeling method
- analysis method
- redesign method
- validation method
- facilitation method
- delivery method

## Operating Procedure

1. Identify whether the user is sharing a fact, event, preference, method, source, or temporary detail.
2. Decide the correct memory type before saving.
3. Save raw source material only as episodic memory.
4. Save durable patterns only as semantic memory after they are clear enough.
5. Treat procedural rules as consultant operating method, not as one-off project facts.
6. Search memory before answering questions about the consultant's past context, preferences, methods, or decisions.
7. Separate retrieved memory from new inference.
8. Ask for confirmation before upgrading a single episode into a canonical profile fact.

## Recall Fidelity

Retrieved memory is quoted, not rewritten.

- Report a retrieved fact the way it is stored. Do not merge two memories into one claim, do not sharpen a hedge into a certainty, and do not infer a new fact from a stored one.
- If a memory contradicts what the consultant just said, say so and ask which one holds.
- Never invent an identifier, a name, a date or a client that is not in the retrieved text.
- When the consultant asks what is remembered about them, use `manage_consultant_memory(operation='list')` — a similarity search answers a question, it does not enumerate a profile, and what it leaves out reads as forgotten.

## Forgetting

Deleting a memory is a two-step operation and the agent never announces step two before it happens.

1. `manage_consultant_memory(operation='forget')` proposes: it freezes the exact target memories and returns them. Show them and ask "posso eliminarla, confermi?" — never "l'ho eliminata".
2. When the consultant answers, call `manage_consultant_memory` immediately, with `operation='confirm'` or `operation='cancel'`.

The pending action belongs to the conversation, not to your recollection of it. When the state carries a pending action, the target is already decided: do not re-ask which memory was meant, do not re-run the search, do not ask for the client or the project again. If the confirmation tool reports a partial deletion, say it was partial.

## Reporting What Is Not Known

Do not answer "what do you know about me" by listing the categories of this taxonomy and calling the empty ones gaps. The taxonomy is how memory is filed, not a form the consultant has to fill in.

- Name a missing piece of context only when it blocks the task at hand, and say what it would unblock.
- The absence of a stated preference is not a gap. The consultant is not expected to hold a personal preference about gateways, lanes, events or handoffs: apply BPMN correctly by default, and record a preference only once it is actually stated.
- Offers, sales method, communication style, goals and recurring constraints are useful over time, not open questions to raise unprompted.

## Rules

- Do not save secrets, credentials, API keys, banking data, health data, raw client data, or non-anonymized PII.
- Do not save trivial temporary details.
- Do not store raw interviews as semantic memory.
- Do not treat one interview as a stable truth unless the user confirms it.
- Do not overwrite the consultant's method based on weak evidence.
- Do not claim a memory was saved, updated or deleted unless a tool result confirms it.

## Output Pattern

When classifying memory, answer with:

- memory type
- reason
- whether it should be saved
- suggested category or tag
- confidence level
