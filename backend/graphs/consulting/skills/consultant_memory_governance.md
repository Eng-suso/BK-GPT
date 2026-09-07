---
name: consultant_memory_governance
description: Decide how the Consult Macro Agent should store, retrieve, and trust consultant-level semantic, episodic, and procedural memory.
---

# Consultant Memory Governance

## Purpose

Use this skill when the Consulting Chat handles memory about Sohay, his consulting method, business context, preferences, decisions, or source-backed events.

## Memory Types

These three types are how memory is filed once something is worth keeping. They
are not a form to complete, and an empty type is not a gap: see "Reporting What
Is Not Known".

Semantic memory stores durable consultant-level facts and stable patterns:

- identity and positioning
- offers and services
- target clients
- delivery and sales style
- recurring preferences
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

- orchestration method
- delegation method
- discovery method
- analysis method
- delivery method

## Operating Procedure

1. Identify whether the user is sharing a durable fact, dated event, reusable method, source, preference, or temporary detail.
2. Search memory before answering questions about Sohay's past context, preferences, method, or decisions.
3. Save stable consultant-level patterns as semantic memory only when they are clear enough.
4. Save raw or dated source material as episodic memory, not semantic memory.
5. Treat procedural rules as agent operating method, not as one-off project facts.
6. Ask for confirmation before turning one event into canonical profile truth.

## Recall Fidelity

Retrieved memory is quoted, not rewritten.

- Report a retrieved fact the way it is stored. Do not merge two memories into one claim, do not sharpen a hedge into a certainty, and do not infer a new fact from a stored one.
- If a memory contradicts what the consultant just said, say so and ask which one holds. Do not silently pick.
- Never invent an identifier, a name, a date or a client that is not in the retrieved text.
- When the consultant asks what is remembered about them, use `manage_consultant_memory(operation='list')` — a similarity search answers a question, it does not enumerate a profile, and what it leaves out reads as forgotten.

## Registering a Method

A reusable method enters procedural memory because the consultant decided it
should, never because you noticed a pattern worth keeping.

1. `manage_consultant_playbook(operation='save_candidate')` proposes: it writes
   nothing and freezes the method for this conversation. Show it and ask whether
   they want it kept as a reusable method — never "l'ho registrato".
2. When they answer, call `operation='confirm_save'` or `operation='cancel_save'`
   immediately. The proposal is already frozen: do not restate it and do not ask
   again what it was about.

A confirmed method is still only a candidate: it is not used until `promote`
passes its guardrail.

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

## Guardrails

- Do not save secrets, credentials, API keys, banking data, health data, raw client data, or non-anonymized PII.
- Do not save trivial temporary details.
- Do not store raw interviews as semantic memory.
- Do not overwrite consultant method from weak evidence.
- Do not claim a memory was saved, updated or deleted unless a tool result confirms it.
