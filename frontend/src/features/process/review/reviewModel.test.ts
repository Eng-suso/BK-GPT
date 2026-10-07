import { describe, expect, it } from "vitest";
import { dependencyScope, inspectReviewNode, readReviewGraph, type ReviewGraph, type ReviewState } from "./reviewModel";

const graph: ReviewGraph = { nodes: ["a", "b", "c", "d", "unrelated"].map(id => ({ id, name: id, type: "userTask", owner: "", refs: [], notes: "" })), edges: [
  { source: "a", target: "b", kind: "sequence" }, { source: "b", target: "gateway", kind: "sequence" },
  { source: "gateway", target: "c", kind: "sequence" }, { source: "gateway", target: "d", kind: "sequence" },
  { source: "d", target: "b", kind: "sequence" }, { source: "form", target: "b", kind: "data" },
] };
const state: ReviewState = { process_id: "p", base_revision: "r", xml: null, actions: [], plan: {
  title: "P", actors: [{ id: "buy", label: "Acquisti" }], steps: [{ id: "verify", label: "Verificare", actor_ids: ["buy"], inputs: ["request"], outputs: [] }], data_objects: [{ id: "request", label: "Richiesta" }], controls: [], consultant_findings: [], structured_business_rules: [],
} };

describe("review dependency scope", () => {
  it("crosses gateways, includes both branches, terminates cycles and excludes unrelated tasks", () => {
    const scope = dependencyScope(graph, "b");
    expect(scope.upstream.map(node => node.id)).toEqual(["a", "d"]);
    expect(scope.downstream.map(node => node.id)).toEqual(["c", "d"]);
    expect(scope.documents).toEqual(["form"]);
  });
  it("joins only exact compiler refs and declares missing output", () => {
    const node = { ...graph.nodes[1], refs: ["steps:verify"] };
    const inspection = inspectReviewNode(node, graph, state);
    expect(inspection.owner).toBe("Acquisti");
    expect(inspection.inputs).toEqual(["Richiesta"]);
    expect(inspection.gaps).toEqual(["output"]);
    const unmatched = inspectReviewNode({ ...node, refs: [], name: "Verificare" }, graph, state);
    expect(unmatched.owner).toBe("");
    expect(unmatched.gaps).toEqual(["owner", "input", "output"]);
  });
  it("reads lanes and namespaced data associations without exposing traceability JSON", () => {
    const xml = `<b:definitions xmlns:b="http://www.omg.org/spec/BPMN/20100524/MODEL"><b:process><b:laneSet><b:lane name="Operations"><b:flowNodeRef>t</b:flowNodeRef></b:lane></b:laneSet><b:userTask id="t" name="Task"><b:documentation>Note\nDeliR traceability: {"source_refs":["steps:s"]}</b:documentation><b:dataInputAssociation><b:sourceRef>data</b:sourceRef><b:targetRef>input</b:targetRef></b:dataInputAssociation></b:userTask></b:process></b:definitions>`;
    const parsed = readReviewGraph(xml);
    expect(parsed.nodes[0]).toMatchObject({ owner: "Operations", refs: ["steps:s"], notes: "Note" });
    expect(parsed.edges).toEqual([{ source: "data", target: "t", kind: "data" }]);
    expect(() => readReviewGraph("<broken")).toThrow("Invalid BPMN XML");
  });
});
