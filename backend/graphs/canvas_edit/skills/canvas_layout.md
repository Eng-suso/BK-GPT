---
name: canvas_layout
description: Arrange BPMN canvas elements so the diagram is readable and ordered.
---

# Canvas Layout

The Layout subgraph owns visual quality only through an explicit consultant
layout plan. It may rebuild BPMN DI shapes and edges, but it must not change
labels, owners, source/target references or business semantics.

The layout flow is agentic:
- read the goal and visible flow nodes;
- split the goal into concrete layout tasks;
- choose readable rows left to right, with start events on the left and end
  events toward the right;
- draw only from that plan;
- block when the plan is missing or incomplete instead of using a hidden
  deterministic fallback.

Good layout means:
- flow nodes do not overlap and have enough spacing;
- long processes wrap into multiple readable rows instead of one very long line;
- lanes cover their elements without creating excessive empty width;
- semantic annotations, associations and data artifacts are removed from the visible operating view before layout;
- sequence flows remain docked and readable;
- sequence flows, message flows and labels are not counted as overlapping elements;
- the canvas can be centered without shrinking below readable scale.

After layout, validate geometry before handing the canvas to semantic validation.
