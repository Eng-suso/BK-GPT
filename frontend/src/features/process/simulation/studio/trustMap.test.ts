import { describe, expect, it } from "vitest";

import type { ActivityGap } from "../eventlog/realVsSimulated";
import type { RunModel } from "./runModel";
import { trustCounts, trustMap } from "./trustMap";

const dur = { kind: "fixed" as const, value: 600 };
const prov = (origin: string, confidence: "high" | "medium" | "low", ids: string[] = []) => ({ origin, confidence, sources: ids.map((id) => ({ kind: "claim", id })) });

const model = {
  calendars: [], gateways: [{ element_id: "G", branches: [{ flow_id: "F1", probability: 0.5, provenance: prov("manual", "high") }, { flow_id: "F2", probability: 0.5 }] }],
  pools: [{ id: "p", name: "Ufficio", resources: [{ id: "r1", name: "Operatore", cost_per_hour: 30, amount: 2, calendar_id: "delir-calendar-standard", shifts: [] }] }],
  activities: [
    { element_id: "A", name: "Ricevi", assignments: [{ resource_id: "r1", duration: dur, provenance: prov("observed", "high", ["c1"]) }] },
    { element_id: "B", name: "Verifica", assignments: [{ resource_id: "r1", duration: dur, provenance: prov("declared", "high", ["c1", "c2"]) }, { resource_id: "r1", duration: dur, provenance: prov("estimated", "low") }] },
    { element_id: "C", name: "Approva", assignments: [{ resource_id: "r1", duration: dur, provenance: prov("observed", "high") }] },
    { element_id: "D", name: "Paga", assignments: [{ resource_id: "r1", duration: dur, provenance: prov("estimated", "low") }] },
    { element_id: "E", name: "Archivia", assignments: [{ resource_id: "r1", duration: dur, provenance: prov("manual", "medium") }] },
  ],
} as unknown as RunModel;

const gap = (el: string, processingGap: number, fidelity: ActivityGap["fidelity"]) => ({ el, processingGap, fidelity } as ActivityGap);

describe("trust map (SIM-20)", () => {
  it("prende il parametro piu' debole, conta le fonti distinte e ordina per intervento", () => {
    const rows = trustMap(model, [], null, [gap("C", 0.6, "far"), gap("D", 0.05, "close")]);
    expect(rows.map((row) => [row.el, row.status])).toEqual([
      ["C", "calibrate"], ["G", "weak"], ["B", "weak"], ["E", "toConfirm"], ["A", "solid"], ["D", "validated"],
    ]);
    const b = rows.find((row) => row.el === "B")!;
    expect(b).toMatchObject({ confidence: "low", origin: "estimated", sources: 2, parameters: 2, gap: null, fidelity: null });
    expect(rows.find((row) => row.el === "C")).toMatchObject({ confidence: "high", gap: 0.6 });
  });

  it("un ramo senza provenienza e' un'ipotesi non dichiarata, non una scelta", () => {
    const g = trustMap(model).find((row) => row.el === "G")!;
    expect(g).toMatchObject({ kind: "gateway", confidence: "low", parameters: 2 });
  });

  it("senza log nessuna attivita' e' validata o da calibrare", () => {
    const rows = trustMap(model);
    expect(rows.some((row) => row.status === "validated" || row.status === "calibrate")).toBe(false);
    expect(trustCounts(rows)).toEqual([{ status: "weak", count: 3 }, { status: "toConfirm", count: 1 }, { status: "solid", count: 2 }]);
  });
});
