---
name: process_modeling
description: Convert evidence-backed process knowledge into ProcessUnderstanding and BPMN semantic structure.
---

# Process Modeling

## Procedure

1. Start from synthesized evidence, not generic assumptions.
2. Build or review ProcessUnderstanding first.
3. Define scope, start event, end event and business outcome.
4. Model actors, lanes, activities, gateways, events, handoffs, exceptions, systems and data only when supported or marked as assumptions.
5. Validate semantic completeness before BPMN notation details.
6. Derive BPMNSemanticModel from ProcessUnderstanding.
7. Preserve unresolved gaps as unknowns or model warnings.

## Quality Gate

Before canvas handoff, check:

- clear start and end
- at least one main path
- known actors or explicit missing actor warning
- decisions have conditions or warnings
- exceptions are modeled or listed as gaps
- assumptions are visible
