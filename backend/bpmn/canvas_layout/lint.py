"""Geometry violations are a write gate; crossing minimization is reported."""
from itertools import combinations, pairwise
from math import isfinite

from .geometry import Box
from .policy import ARTIFACT_TYPES, BPMNDI, DC, DI, FLOW_TYPES, local_name, tag
from .router import segment_hits_box, _cross


def lint_visual_model(root) -> dict:
    elements = {e.get("id"): e for e in root.iter() if e.get("id")}
    shapes, labels = {}, {}
    issues, warnings = [], []
    counts = {}
    for shape in root.iter(f"{{{BPMNDI}}}BPMNShape"):
        ref = shape.get("bpmnElement")
        counts[ref] = counts.get(ref, 0) + 1
        bounds = shape.find(f"{{{DC}}}Bounds")
        if bounds is None:
            issues.append(f"Forma senza bounds: {ref}.")
            continue
        try:
            box = Box(*(float(bounds.get(key, "nan")) for key in ("x", "y", "width", "height")))
            if not all(isfinite(value) for value in (box.x, box.y, box.width, box.height)) or min(box.width, box.height) <= 0:
                raise ValueError
        except ValueError:
            issues.append(f"Bounds non validi: {ref}.")
            continue
        shapes[ref] = box
        label = shape.find(f"{{{BPMNDI}}}BPMNLabel/{{{DC}}}Bounds")
        if label is not None:
            labels[ref] = Box(*(float(label.get(key)) for key in ("x", "y", "width", "height")))
    for ref, element in elements.items():
        if local_name(element) in FLOW_TYPES | ARTIFACT_TYPES | {"participant", "lane"} and counts.get(ref) != 1:
            issues.append(f"L'elemento {ref} deve avere una sola forma DI.")
    visible = {ref: box for ref, box in shapes.items() if ref in elements and local_name(elements[ref]) in FLOW_TYPES | ARTIFACT_TYPES}
    for (left, a), (right, b) in combinations(visible.items(), 2):
        if elements[left].get("attachedToRef") == right or elements[right].get("attachedToRef") == left:
            continue
        if _overlap(a, b):
            issues.append(f"Elementi sovrapposti: {left}, {right}.")
    for lane in root.iter(tag("lane")):
        box = shapes.get(lane.get("id"))
        for ref in lane.findall(tag("flowNodeRef")):
            child = shapes.get(ref.text)
            if box and child and not _contains(box, child):
                issues.append(f"Il nodo {ref.text} è fuori dalla lane del suo owner.")
    routes, edge_counts, edge_crossings = [], {}, 0
    for edge in root.iter(f"{{{BPMNDI}}}BPMNEdge"):
        ref = edge.get("bpmnElement")
        edge_counts[ref] = edge_counts.get(ref, 0) + 1
        points = [(float(e.get("x")), float(e.get("y"))) for e in edge.findall(f"{{{DI}}}waypoint")]
        if len(points) < 2 or any(not all(isfinite(value) for value in point) for point in points):
            issues.append(f"Collegamento senza percorso valido: {ref}.")
            continue
        if any(a[0] != b[0] and a[1] != b[1] for a, b in pairwise(points)):
            issues.append(f"Collegamento non ortogonale: {ref}.")
        semantic = elements.get(ref)
        if semantic is not None and local_name(semantic) == "sequenceFlow":
            source, target = semantic.get("sourceRef"), semantic.get("targetRef")
            for node_id, box in visible.items():
                if node_id in {source, target}:
                    continue
                if any(segment_hits_box(a, b, box) for a, b in pairwise(points)):
                    issues.append(f"Il flusso {ref} attraversa {node_id}.")
            for old_source, old_target, old_points in routes:
                if {source, target}.intersection({old_source, old_target}):
                    continue
                edge_crossings += sum(_cross(a, b, c, d) for a, b in pairwise(points) for c, d in pairwise(old_points))
            routes.append((source, target, points))
    for flow in root.iter(tag("sequenceFlow")):
        if edge_counts.get(flow.get("id")) != 1:
            issues.append(f"Il flusso {flow.get('id')} deve avere una sola linea DI.")
    if edge_crossings:
        warnings.append(f"Incroci residui tra flussi: {edge_crossings}.")
    return {"valid": not issues, "issues": sorted(set(issues)), "warnings": warnings, "metrics": {"shapes": len(shapes), "sequence_flows": len(routes), "edge_crossings": edge_crossings}}


def _overlap(a, b):
    return a.x < b.right and a.right > b.x and a.y < b.bottom and a.bottom > b.y


def _contains(container, child):
    return container.x <= child.x and container.y <= child.y and container.right >= child.right and container.bottom >= child.bottom
