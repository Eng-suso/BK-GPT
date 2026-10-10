import { describe, expect, it } from "vitest";

import { describeChanges, type ChangeLabels } from "./scenarioChanges";
import type { ScenarioPatchOp } from "./scenarioPatch";

const LABELS: ChangeLabels = {
  field: (key) => `campo:${key}`,
  section: (key) => `sezione:${key}`,
  number: (value) => String(value),
  complex: "modificato",
  text: (key, value) => (key === "distribution" ? `dist:${value}` : value),
  yes: "sì",
  no: "no",
};
const AS_IS = {
  totalCases: 100,
  resources: [{ id: "approver", name: "Approvatore", amount: 1 }],
  tasks: { T1: { meanMinutes: 30, resourceId: "approver" } },
  calendars: [{ id: "cal", name: "Turno", periods: [] }],
};
const NAMES = { elements: { T1: "Approva ordine" }, resources: { approver: "Approvatore", senior: "Senior" } };

const read = (patch: ScenarioPatchOp[], conflicts: number[] = []) => describeChanges(patch, conflicts, AS_IS, NAMES, LABELS);

describe("describeChanges", () => {
  it("una risorsa per id: nome, campo, prima e dopo", () => {
    expect(read([{ op: "set", path: ["resources", { id: "approver" }, "amount"], value: 2 }])[0]).toMatchObject({
      elementId: null, subject: "Approvatore", field: "campo:amount", kind: "changed", from: "1", to: "2", conflict: false,
    });
  });

  it("un'attivita': l'elemento del BPMN e la risorsa per nome", () => {
    expect(read([{ op: "set", path: ["tasks", "T1", "resourceId"], value: "senior" }])[0]).toMatchObject({
      elementId: "T1", subject: "Approva ordine", field: "campo:resourceId", from: "Approvatore", to: "Senior",
    });
  });

  it("un valore testuale tradotto e un ramo col suo nome", () => {
    const names = { ...NAMES, elements: { ...NAMES.elements, G1: "Importo alto?", f1: "Ramo verso Approva" } };
    const [dist, branch] = describeChanges(
      [
        { op: "set", path: ["tasks", "T1", "distribution"], value: "expon" },
        { op: "set", path: ["gateways", "G1", "f1"], value: 30 },
      ],
      [], AS_IS, names, LABELS,
    );
    expect(dist).toMatchObject({ to: "dist:expon", kind: "added" });
    expect(branch).toMatchObject({ elementId: "G1", subject: "Importo alto?", field: "Ramo verso Approva", to: "30" });
  });

  it("un campo dello scenario e una sezione nuova", () => {
    const [cases, sla] = read([
      { op: "set", path: ["totalCases"], value: 200 },
      { op: "set", path: ["sla"], value: { target: 2 } },
    ]);
    expect(cases).toMatchObject({ subject: "sezione:totalCases", field: "", kind: "changed", from: "100", to: "200" });
    expect(sla).toMatchObject({ subject: "sezione:sla", kind: "added", from: null, to: "modificato" });
  });

  it("un elemento aggiunto, uno tolto, un ordine e un conflitto", () => {
    const changes = read(
      [
        { op: "set", path: ["resources", { id: "bot" }], value: { id: "bot", name: "Bot" } },
        { op: "remove", path: ["calendars", { id: "cal" }] },
        { op: "order", path: ["resources"], ids: ["bot", "approver"] },
        { op: "set", path: ["tasks", "T9", "meanMinutes"], value: 5 },
      ],
      [3],
    );
    expect(changes[0]).toMatchObject({ subject: "Bot", kind: "added", to: "Bot" });
    expect(changes[1]).toMatchObject({ subject: "Turno", kind: "removed", to: null });
    expect(changes[2]).toMatchObject({ subject: "sezione:resources", field: "", kind: "reordered" });
    expect(changes[3]).toMatchObject({ elementId: "T9", subject: "T9", kind: "added", conflict: true });
  });
});
