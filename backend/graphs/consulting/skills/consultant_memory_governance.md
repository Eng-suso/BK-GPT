---
name: consultant_memory_governance
description: Decide how the Consult Macro Agent should store, retrieve, and trust consultant-level semantic, episodic, and procedural memory.
---

# Consultant Memory Governance

## Purpose

Use this skill when the Consulting Chat handles memory about Sohay, his consulting method, business context, preferences, decisions, or source-backed events.

## Memory Types

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

## Guardrails

- Do not save secrets, credentials, API keys, banking data, health data, raw client data, or non-anonymized PII.
- Do not save trivial temporary details.
- Do not store raw interviews as semantic memory.
- Do not overwrite consultant method from weak evidence.
