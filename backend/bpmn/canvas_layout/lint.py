"""Geometry violations are a write gate; crossing minimization is reported."""
from itertools import combinations, pairwise
from math import isfinite

from .geometry import Box
from .policy import ARTIFACT_TYPES, BPMNDI, DC, DI, FLOW_TYPES, local_name, tag
from .router import segment_hits_box, _cross


def lint_visual_model(root, *, manual: bool = False) -> dict:
    elements = {e.get("id"): e for e in root.iter() if e.get("id")}
    shapes, labels = {}, {}
    issues, warnings = [], []
    counts = {}
    for shape in root.iter(f"{{{BPMNDI}}}BPMNShape"):
        ref = shape.get("bpmnElement")
        if ref not in elements:
            issues.append(f"Forma con riferimento semantico sconosciuto: {ref}.")
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
            try:
                label_box = Box(*(float(label.get(key, "nan")) for key in ("x", "y", "width", "height")))
                if not all(isfinite(v) for v in (label_box.x, label_box.y, label_box.width, label_box.height)) or min(label_box.width, label_box.height) <= 0:
                    raise ValueError
                labels[ref] = label_box
            except ValueError:
                issues.append(f"Bounds etichetta non validi: {ref}.")
    hidden = {e.get("id") for sub in root.iter(tag("subProcess")) for e in sub.iter() if e is not sub}
    for ref, element in elements.items():
        if ref in hidden:
            continue
        if local_name(element) in FLOW_TYPES | ARTIFACT_TYPES | {"participant", "lane"} and counts.get(ref) != 1:
            issues.append(f"L'elemento {ref} deve avere una sola forma DI.")
    visible = {ref: box for ref, box in shapes.items() if ref in elements and local_name(elements[ref]) in FLOW_TYPES | ARTIFACT_TYPES}
    for (left, a), (right, b) in combinations(visible.items(), 2):
        if elements[left].get("attachedToRef") == right or elements[right].get("attachedToRef") == left:
            continue
        if _overlap(a, b):
            issues.append(f"Elementi sovrapposti: {left}, {right}.")
    for label_id, label in labels.items():
        for ref, box in visible.items():
            if _overlap(label, box):
                (warnings if manual else issues).append(f"Etichetta {label_id} sovrapposta a {ref}.")
    for (left, a), (right, b) in combinations(labels.items(), 2):
        if _overlap(a, b):
            (warnings if manual else issues).append(f"Etichette sovrapposte: {left}, {right}.")
    for participant in root.iter(tag("participant")):
        container = shapes.get(participant.get("id"))
        process = elements.get(participant.get("processRef"))
        if container and process is not None:
            for node in process:
                child = shapes.get(node.get("id"))
                if child and not _contains(container, child):
                    issues.append(f"Il nodo {node.get('id')} è fuori dalla pool del processo.")
                label = labels.get(node.get("id"))
                if label and not _contains(container, label):
                    (warnings if manual else issues).append(f"Etichetta {node.get('id')} fuori dalla pool.")
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
        try:
            points = [(float(e.get("x", "nan")), float(e.get("y", "nan"))) for e in edge.findall(f"{{{DI}}}waypoint")]
        except ValueError:
            issues.append(f"Coordinate collegamento non valide: {ref}.")
            continue
        if ref not in elements:
            issues.append(f"Collegamento con riferimento sconosciuto: {ref}.")
        if len(points) < 2 or any(not all(isfinite(value) for value in point) for point in points):
            issues.append(f"Collegamento senza percorso valido: {ref}.")
            continue
        if any(a[0] != b[0] and a[1] != b[1] for a, b in pairwise(points)):
            (warnings if manual else issues).append(f"Collegamento non ortogonale: {ref}.")
        for label_id, label in labels.items():
            if any(segment_hits_box(a, b, label) for a, b in pairwise(points)):
                (warnings if manual else issues).append(f"Il flusso {ref} attraversa l'etichetta {label_id}.")
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
        if flow.get("id") in hidden:
            continue
        if edge_counts.get(flow.get("id")) != 1:
            issues.append(f"Il flusso {flow.get('id')} deve avere una sola linea DI.")
    if edge_crossings:
        warnings.append(f"Incroci residui tra flussi: {edge_crossings}.")
    return {"valid": not issues, "issues": sorted(set(issues)), "warnings": warnings, "metrics": {"shapes": len(shapes), "sequence_flows": len(routes), "edge_crossings": edge_crossings}}


def _overlap(a, b):
    return a.x < b.right and a.right > b.x and a.y < b.bottom and a.bottom > b.y


def _contains(container, child):
    return container.x <= child.x and container.y <= child.y and container.right >= child.right and container.bottom >= child.bottom
