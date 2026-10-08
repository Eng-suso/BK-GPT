---
name: canvas_layout
description: Request product-owned BPMN layout and inspect its validation.
---

# Canvas Layout

DeliR owns geometry. Agents change semantic nodes, owners and connections only.
Every agent mutation passes through semantic normalization, CanvasLayoutPolicy,
orthogonal routing and visual lint before regenerated BPMN DI reaches the canvas.
Do not supply coordinates, dimensions, rows, routing or visual lane order.

The global policy derives left-to-right ranks from sequence flows, real-owner
lanes ordered by first involvement, symmetric branches and joins, and routes
that avoid nodes. Preserve documents, conditions, annotations and provenance.
Invalid geometry blocks writes. Remaining unavoidable crossings are reported.
Manual consultant geometry stays intact and is validated without relayout.
