import { describe, expect, it } from "vitest";
import { connectionRule } from "./connectionRules";
import { businessObject, type CanvasElement } from "./types";
const node = (type: string, parent?: CanvasElement, message = false): CanvasElement => ({id:crypto.randomUUID(),type:"bpmn:"+type,businessObject:businessObject("bpmn:"+type,{eventDefinitions:message?[{$type:"bpmn:MessageEventDefinition"}]:[]}),parent,x:0,y:0,width:100,height:80});
describe("BPMN collaboration connection rules", () => {
  const root=node("Collaboration"), pool=node("Participant",root), other=node("Participant",root), lane=node("Lane",pool), sibling=node("Lane",pool);
  it("uses sequence flow between lanes in the same participant",()=>expect(connectionRule(node("UserTask",lane),node("Task",sibling))).toEqual({type:"bpmn:SequenceFlow"}));
  it("uses message flow between separate participants, including their boundaries",()=>{
    expect(connectionRule(node("SendTask",lane),node("ReceiveTask",other))).toEqual({type:"bpmn:MessageFlow"});
    expect(connectionRule(pool,other)).toEqual({type:"bpmn:MessageFlow"});
    expect(connectionRule(pool,node("Task",other))).toEqual({type:"bpmn:MessageFlow"});
  });
  it("rejects lane endpoints, same-pool participant links and cross-pool gateways",()=>{
    expect(connectionRule(lane,sibling)).toBe(false);
    expect(connectionRule(pool,node("Task",lane))).toBe(false);
    expect(connectionRule(node("ExclusiveGateway",lane),node("Task",other))).toBe(false);
  });
  it("accepts only correctly directed message events across participants",()=>{
    expect(connectionRule(node("EndEvent",lane,true),node("StartEvent",other,true))).toEqual({type:"bpmn:MessageFlow"});
    expect(connectionRule(node("EndEvent",lane),node("StartEvent",other))).toBe(false);
    expect(connectionRule(node("IntermediateCatchEvent",lane,true),node("Task",other))).toBe(false);
  });
  it("rejects sequence flows into starts and boundaries, out of ends or across subprocess scope",()=>{
    const task=node("Task",lane);
    expect(connectionRule(task,node("StartEvent",sibling))).toBe(false);
    expect(connectionRule(task,node("BoundaryEvent",sibling))).toBe(false);
    expect(connectionRule(node("EndEvent",lane),task)).toBe(false);
    expect(connectionRule(task,node("Task",node("SubProcess",pool)))).toBe(false);
  });
});
