import { describe, it, expect } from "vitest";
import { copiedBusinessObject } from "./clipboard";
import { NS } from "./types";
describe("BPMN clipboard", () => {
    it("keeps opaque extensions and timer definitions while giving copied semantic elements new IDs", () => {
        const xml = '<bpmn:subProcess xmlns:bpmn="' + NS.bpmn + '" xmlns:v="urn:vendor" id="original"><bpmn:extensionElements><v:payload>keep</v:payload></bpmn:extensionElements><bpmn:startEvent id="hidden"><bpmn:timerEventDefinition id="timer"><bpmn:timeDuration>PT5M</bpmn:timeDuration></bpmn:timerEventDefinition></bpmn:startEvent><bpmn:userTask id="visible"/></bpmn:subProcess>';
        const bo = copiedBusinessObject("bpmn:SubProcess", { name: "Copied", $attrs: { "delir:owner": "Operations" } }, "copy", xml, new Set(["visible"]));
        const doc = new DOMParser().parseFromString(String(bo.sourceXml), "application/xml");
        expect(doc.documentElement.id).toBe("copy");
        expect(doc.getElementById("visible")).toBeNull();
        expect(doc.getElementById("hidden")).toBeNull();
        expect(doc.getElementById("timer")).toBeNull();
        expect(doc.getElementsByTagNameNS(NS.bpmn, "timeDuration")[0].textContent).toBe("PT5M");
        expect(doc.getElementsByTagNameNS("urn:vendor", "payload")[0].textContent).toBe("keep");
        expect(bo.get("delir:owner")).toBe("Operations");
    });
    it("keeps copied pools and groups independent from the original semantic definitions", () => {
        for (const [type, tag, ref] of [["Participant", "participant", "processRef"], ["Group", "group", "categoryValueRef"]]) {
            const bo = copiedBusinessObject("bpmn:" + type, {}, "copy", '<bpmn:' + tag + ' xmlns:bpmn="' + NS.bpmn + '" id="old" ' + ref + '="original"/>');
            expect(new DOMParser().parseFromString(String(bo.sourceXml), "application/xml").documentElement.hasAttribute(ref)).toBe(false);
        }
    });
});
