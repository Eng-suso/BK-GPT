import {expect,it} from "vitest";
import {creationGroup,enterpriseEntries} from "./enterprisePalette";

it("places event variants and the event-based gateway in their semantic categories",()=>{
  for(const entry of enterpriseEntries)expect(creationGroup(entry.target.type)).toBe(entry.group);
  expect(creationGroup("bpmn:DataObjectReference")).toBe("data");
  expect(creationGroup("bpmn:DataStoreReference")).toBe("data");
  expect(creationGroup("bpmn:Group")).toBe("artifact");
});
