---
name: process_modeling
description: Convert validated process understanding into a BPMN-ready process model. Use for BPMN, As-Is modeling, actors, lanes, pools, activities, gateways, events, handoffs, exceptions, systems, data objects, and model quality checks.
---

# Process Modeling

## Purpose

Use this skill to convert validated process understanding into a BPMN-ready process model.

## Operating Procedure

1. Start from synthesized evidence, not from generic process assumptions.
2. Define the process scope, start event, end event, and business outcome.
3. Identify pools, lanes, actors, and systems only when supported by evidence or explicitly marked as assumptions.
4. Extract activities and name them as action-oriented tasks.
5. Identify sequence flow and handoffs.
6. Identify decisions and represent them as gateways only when the decision changes the path.
7. Identify events, messages, timers, exceptions, and escalations.
8. Identify information objects and systems when relevant to understanding the process.
9. Check semantic completeness before BPMN notation details.
10. Mark unresolved gaps and assumptions directly in the model notes.

## Rules

- Do not model an actor only because it seems plausible.
- Do not transform a hypothesis into a confirmed As-Is element.
- Do not over-model cosmetic BPMN details before the process semantics are clear.
- Every important As-Is element should be traceable to evidence or marked as an assumption.
- Keep official process and actual process distinct when they diverge.

## Quality Checks

Before treating the model as usable, check:

- clear start and end
- no orphan activities
- named actors for handoffs
- decisions have explicit conditions
- exceptions are represented or listed as gaps
- assumptions are visible
- evidence coverage is acceptable

## Output Pattern

Return:

- process scope
- actors and lanes
- activities
- decisions and gateways
- handoffs
- events and exceptions
- data and systems
- assumptions and evidence gaps
- BPMN-ready structure
