import { describe, expect, it } from "vitest";
import { readPlainProcess } from "./plainProcess";

const wrap = (body: string) => `<?xml version="1.0"?><b:definitions xmlns:b="http://www.omg.org/spec/BPMN/20100524/MODEL"><b:process id="P">${body}</b:process></b:definitions>`;
const flow = (id: string, source: string, target: string, name = "") => `<b:sequenceFlow id="${id}" sourceRef="${source}" targetRef="${target}"${name ? ` name="${name}"` : ""}/>`;

const PURCHASE = wrap(`
<b:laneSet><b:lane id="L1" name="Richiedente"><b:flowNodeRef>start</b:flowNodeRef><b:flowNodeRef>request</b:flowNodeRef></b:lane>
<b:lane id="L2" name="Amministrazione"><b:flowNodeRef>amount</b:flowNodeRef><b:flowNodeRef>sign</b:flowNodeRef><b:flowNodeRef>join</b:flowNodeRef><b:flowNodeRef>order</b:flowNodeRef></b:lane></b:laneSet>
<b:startEvent id="start" name="Serve un acquisto"/>
<b:userTask id="request" name="Compilare la&#10;richiesta"/>
<b:exclusiveGateway id="amount" name="Importo sopra 5.000 €?"/>
<b:userTask id="sign" name="Seconda firma"/>
<b:exclusiveGateway id="join"/>
<b:userTask id="order" name="Emettere l'ordine"/>
<b:endEvent id="end" name="Ordine inviato"/>
${flow("f1", "start", "request")}${flow("f2", "request", "amount")}
${flow("f3", "amount", "sign", "Sì")}${flow("f4", "amount", "join", "No")}
${flow("f5", "sign", "join")}${flow("f6", "join", "order")}${flow("f7", "order", "end")}`);

describe("plain process", () => {
  it("lists steps in the order they happen, with who does them, and skips merge points", () => {
    const plain = readPlainProcess(PURCHASE);
    expect(plain.starts).toEqual(["Serve un acquisto"]);
    expect(plain.ends).toEqual(["Ordine inviato"]);
    expect(plain.steps.map((step) => [step.number, step.kind, step.name, step.actor])).toEqual([
      [1, "activity", "Compilare la richiesta", "Richiedente"],
      [2, "decision", "Importo sopra 5.000 €?", "Amministrazione"],
      [3, "activity", "Seconda firma", "Amministrazione"],
      [4, "activity", "Emettere l'ordine", "Amministrazione"],
    ]);
    expect(plain.actors).toEqual([{ name: "Richiedente", steps: 1 }, { name: "Amministrazione", steps: 2 }]);
  });

  it("writes decisions as answers that lead to a step, jumping over merge points", () => {
    const decision = readPlainProcess(PURCHASE).steps[1];
    expect(decision.next).toEqual([{ kind: "step", number: 3, label: "Sì" }, { kind: "step", number: 4, label: "No" }]);
    expect(readPlainProcess(PURCHASE).steps[3].next).toEqual([{ kind: "end", name: "Ordine inviato", label: "" }]);
  });

  it("survives loops, parallel work, waits and unreachable steps", () => {
    const plain = readPlainProcess(wrap(`
<b:startEvent id="s"/><b:userTask id="a" name="Controllare"/><b:parallelGateway id="split"/>
<b:userTask id="b" name="Avvisare"/><b:userTask id="c" name="Archiviare"/><b:intermediateCatchEvent id="w" name="Attendere 2 giorni"/>
<b:userTask id="orphan" name="Passo isolato"/><b:endEvent id="e"/>
${flow("1", "s", "a")}${flow("2", "a", "split")}${flow("3", "split", "b")}${flow("4", "split", "c")}
${flow("5", "b", "w")}${flow("6", "w", "a", "Ripetere")}${flow("7", "c", "e")}`));
    expect(plain.steps.map((step) => `${step.number}:${step.kind}:${step.name}`)).toEqual([
      "1:activity:Controllare", "2:parallel:", "3:activity:Avvisare", "4:activity:Archiviare", "5:wait:Attendere 2 giorni", "6:activity:Passo isolato",
    ]);
    expect(plain.steps[4].next).toEqual([{ kind: "step", number: 1, label: "Ripetere" }]);
    expect(plain.steps[0].actor).toBe("");
  });

  it("shows a sub-process as one step and returns nothing for a missing or broken diagram", () => {
    const plain = readPlainProcess(wrap(`<b:startEvent id="s"/><b:subProcess id="sp" name="Gestire il reso"><b:userTask id="inner" name="Dentro"/></b:subProcess>${flow("1", "s", "sp")}`));
    expect(plain.steps.map((step) => step.name)).toEqual(["Gestire il reso"]);
    expect(readPlainProcess(null).steps).toEqual([]);
    expect(readPlainProcess("<broken").steps).toEqual([]);
  });
});
