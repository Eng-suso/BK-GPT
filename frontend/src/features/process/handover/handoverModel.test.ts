import { describe, expect, it } from "vitest";
import type { ConformanceStatus, ProcessProvenance } from "@/contracts/workspace";
import type { SimulationRun } from "../simulation/simulationTypes";
import type { ReviewAction, ReviewState } from "../review/reviewModel";
import { buildReadiness, buildTimeline, changesWithEvidence, latestCompletedRun, openPoints, stageFromStatus } from "./handoverModel";

const XML = `<?xml version="1.0"?><definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"><process id="p">
<userTask id="approve" name="Approvare"><documentation>DeliR traceability: {"source_refs":["steps:approve"]}</documentation></userTask>
<userTask id="pay" name="Pagare"/></process></definitions>`;

const action = (id: string, kind: ReviewAction["kind"], node_id = "approve"): ReviewAction => ({
  id, node_id, node_name: node_id, base_revision: "r1", kind, title: id, detail: "", created_at: "2026-10-01T10:00:00Z", created_by: "consultant",
});
const review = (actions: ReviewAction[], xml: string | null = XML): ReviewState => ({ process_id: "p", base_revision: "r1", xml, plan: null, actions });
const provenance = (ratio: number, awaiting = 0): ProcessProvenance => ({
  processId: "p", snapshotLabel: "", hasPlan: true, total: 2, verified: 1, paraphrased: 0, labelGrounded: 0, unverified: 1,
  awaitingConfirmation: awaiting, groundedRatio: ratio, sourcesChecked: 1, unusedSources: [],
  elements: [{ kind: "step", elementId: "approve", label: "Approvare", status: "verified", markStatus: "verified", sourceRef: "steps:approve", sourceName: "PROC-14", quote: "Seconda firma sopra 5k", consultantDecision: null, removable: false }],
});
const conformance = (severities: Array<"blocking" | "gap">): ConformanceStatus => ({
  processId: "p", running: false, isCurrent: true,
  report: { verdict: "conformant", findings: severities.map((severity) => ({ area: "source_coverage", severity, message: "", sourceName: "" })), sourcesAudited: 1, sourcesWithText: 1, note: "", auditedAt: "" },
});
const run = (id: number, status: SimulationRun["status"], completed_at: string | null): SimulationRun => ({
  id, bpmn_model_id: "m", process_id: "p", scenario_name: `S${id}`, engine: "prosimos", status, request: {}, scenario: {}, result: {}, outputs: [],
  summary: status === "completed" ? ({} as SimulationRun["summary"]) : null, error: null, created_at: "2026-10-01T00:00:00Z", completed_at,
});

describe("handover stage", () => {
  it("reads the stage from the process status the backend already stores", () => {
    expect(stageFromStatus("Bozza")).toBe("design");
    expect(stageFromStatus("In corso")).toBe("design");
    expect(stageFromStatus("Da validare")).toBe("review");
    expect(stageFromStatus("Validato")).toBe("approved");
  });
});

describe("handover readiness", () => {
  it("is ready when the model, the owner and the sources hold", () => {
    const result = buildReadiness({ owner: "Finance", review: review([]), provenance: provenance(0.94), conformance: conformance([]), runs: [run(1, "completed", "2026-10-02")] });
    expect(result.ready).toBe(true);
    expect(result.checks.every((check) => check.outcome === "pass")).toBe(true);
    expect(result.checks.find((check) => check.id === "evidence")?.count).toBe(94);
  });

  it("blocks the hand over without a model, an owner or with contradicting sources", () => {
    const result = buildReadiness({ owner: " ", review: review([], null), provenance: null, conformance: conformance(["blocking", "gap"]), runs: [] });
    expect(result.ready).toBe(false);
    expect(result.blocking).toBe(3);
    expect(result.checks.find((check) => check.id === "sources")?.count).toBe(1);
  });

  it("warns, without blocking, on open questions, missing simulation and unchecked sources", () => {
    const result = buildReadiness({ owner: "Finance", review: review([action("q", "clarification"), action("d", "deferred"), action("c", "candidate")]), provenance: provenance(0.6, 2), conformance: null, runs: [run(1, "failed", null)] });
    expect(result.ready).toBe(true);
    const outcome = Object.fromEntries(result.checks.map((check) => [check.id, check.outcome]));
    expect(outcome).toMatchObject({ sources: "warning", evidence: "warning", simulation: "warning", openPoints: "warning" });
    expect(result.checks.find((check) => check.id === "openPoints")?.count).toBe(2);
  });

  it("does not treat an unreadable diagram as a crash", () => {
    const result = buildReadiness({ owner: "Finance", review: review([], "<not-bpmn"), provenance: null, conformance: null, runs: [] });
    expect(result.checks[0]).toMatchObject({ id: "model", outcome: "fail" });
  });
});

describe("handover content", () => {
  it("links each proposed change to the sources of the step it touches, by id only", () => {
    const changes = changesWithEvidence(review([action("c1", "candidate"), action("c2", "candidate", "pay"), action("q", "clarification")]), provenance(0.9));
    expect(changes.map((change) => change.id)).toEqual(["c1", "c2"]);
    expect(changes[0].evidence).toEqual([{ sourceName: "PROC-14", quote: "Seconda firma sopra 5k", markStatus: "verified" }]);
    expect(changes[1].evidence).toEqual([]);
  });

  it("lists open questions and picks the latest completed simulation", () => {
    expect(openPoints(review([action("q", "clarification"), action("c", "candidate")])).map((item) => item.id)).toEqual(["q"]);
    expect(latestCompletedRun([run(1, "completed", "2026-10-02T00:00:00Z"), run(2, "completed", "2026-10-05T00:00:00Z"), run(3, "pending", null)])?.id).toBe(2);
    expect(latestCompletedRun([])).toBeNull();
  });
});

describe("owner dashboard timeline", () => {
  it("merges versions and review entries, newest first, and drops undated or internal ones", () => {
    const versions = [
      { id: 1, changeSummary: "Prima bozza", createdAt: "2026-10-01T09:00:00Z" },
      { id: 2, changeSummary: "To-Be", createdAt: "2026-10-06T09:00:00Z" },
      { id: 3, changeSummary: "Senza data", createdAt: "not-a-date" },
    ];
    const actions = [
      { ...action("c", "candidate"), created_at: "2026-10-03T09:00:00Z" },
      { ...action("q", "clarification"), created_at: "2026-10-07T09:00:00Z" },
      { ...action("a", "as_is_proposal"), created_at: "2026-10-08T09:00:00Z" },
    ];
    const timeline = buildTimeline(versions, review(actions));
    expect(timeline.map((event) => event.id)).toEqual(["action-q", "version-2", "action-c", "version-1"]);
    expect(timeline[0]).toMatchObject({ kind: "request", activity: "approve" });
    expect(buildTimeline(versions, null, 1)).toHaveLength(1);
  });
});
