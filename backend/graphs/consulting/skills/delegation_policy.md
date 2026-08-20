---
name: delegation_policy
description: Define when and how the Consult Macro Agent delegates to Home, Clients, Project, Process, or Canvas agents.
---

# Delegation Policy

## Purpose

Use this skill whenever the Consulting Chat must decide which agent should own the next action.

## Principle

The macro agent decides where work belongs. The specialized agent executes the work.

## Delegation Matrix

| User intent | Owner |
| --- | --- |
| Strategy, positioning, offers, priorities | Consult Macro Agent |
| Consultant memory or preferences | Consult Macro Agent |
| Home dashboard, global priorities, next actions | Home subagent |
| Client creation or update | Clients subagent |
| Project creation, update, phase, next step | Project Macro Agent |
| Project sources, decisions, deliverables | Project Macro Agent |
| AS-IS discovery, evidence synthesis, readiness | Process Macro Agent |
| BPMN semantic model or process review | Process Macro Agent |
| BPMN XML, canvas edit, validation, layout, versions | Canvas Macro Agent |

## Operating Procedure

1. Decide the owner from the user's latest intent and the active UI/backend scope.
2. Keep the delegation payload narrow: user intent, known ids, relevant context, and expected outcome.
3. Do not include unrelated memory or all chat history in the delegation payload.
4. If the owner is unclear, ask one focused question.
5. After delegation, summarize the result and next step for the user.

## Tool Budget

No macro agent or subagent should expose more than 8 direct tools.

If a responsibility needs more than 8 tools, split it into a narrower subagent or tool facade.

## Guardrails

- Do not delegate just to avoid answering a strategic question.
- Do not execute low-level operations in Consult Macro when a specialized owner exists.
- Do not let specialized agents mutate outside their ownership boundary.
