---
name: canvas_layout
description: Arrange BPMN canvas elements so the diagram is readable and ordered.
---

# Canvas Layout

The Layout subgraph owns visual quality only. It may rebuild BPMN DI shapes and
edges, but it must not change labels, owners, source/target references or
business semantics.

Good layout means:
- flow nodes do not overlap and have enough spacing;
- long processes wrap into multiple readable rows instead of one very long line;
- lanes cover their elements without creating excessive empty width;
- semantic annotations, associations and data artifacts are removed from the visible operating view before layout;
- sequence flows remain docked and readable;
- the canvas can be centered without shrinking below readable scale.

After layout, validate geometry before handing the canvas to semantic validation.
