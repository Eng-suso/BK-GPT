import {describe,expect,it} from "vitest";
import {readFileSync} from "node:fs";
import {bpmnIconClass} from "./iconClass";
import {enterpriseEntries} from "./enterprisePalette";

describe("BPMN catalog symbols",()=>{
  it("uses the target symbol for replace and append instead of the settings icon",()=>{
    expect(bpmnIconClass("replace.create.service-task")).toBe("bpmn-icon-service-task");
    expect(bpmnIconClass("replace.create.script-task")).toBe("bpmn-icon-script-task");
    expect(bpmnIconClass("append.task")).toBe("bpmn-icon-task");
    expect(bpmnIconClass("replace.create.call-activity")).toBe("bpmn-icon-call-activity");
  });
  it("resolves every supported catalog element to a glyph present in the installed font",()=>{
    const css=readFileSync("node_modules/bpmn-font/dist/css/bpmn-codes.css","utf8");
    const ids=[...enterpriseEntries.map(entry=>entry.id),...['task','start-event','end-event','intermediate-event','exclusive-gateway','participant-expanded','data-object','data-store','group'].map(id=>"create."+id)];
    for(const id of ids){const symbol=bpmnIconClass(id);expect(symbol,id).toBeTruthy();expect(css,id).toContain("."+symbol+":before");expect(bpmnIconClass("replace."+id),id).toBe(symbol);}
  });
});
