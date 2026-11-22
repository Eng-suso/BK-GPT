import { describe, expect, it } from "vitest";
import { canMoveElements } from "./moveRules";
import { businessObject, type CanvasElement } from "./types";

const shape = (id:string,type:string,parent?:CanvasElement):CanvasElement => ({id,type,parent,businessObject:businessObject(type,{id}),x:60,y:20,width:40,height:40});
function graph() {
  const root=shape("root","bpmn:Process"), pool={...shape("pool","bpmn:Participant",root),x:0,y:100,width:600,height:300};
  const a=shape("a","bpmn:Task",root), b={...shape("b","bpmn:Task",root),x:200};
  const edge={...shape("flow","bpmn:SequenceFlow",root),source:a,target:b,waypoints:[{x:100,y:40},{x:200,y:40}]};
  return {root,pool,a,b,edge,elements:[root,pool,a,b,edge]};
}
describe("subgraph pool adoption",()=>{
  it("allows a complete connected selection, with or without its explicit edge",()=>{
    const {pool,a,b,edge,elements}=graph();
    expect(canMoveElements([a,b],pool,elements,{x:0,y:150})).toBe(true);
    expect(canMoveElements([a,b,edge],pool,elements,{x:0,y:150})).toBe(true);
  });
  it("rejects a partial transfer that would leave a sequence flow crossing pools",()=>{
    const {pool,a,elements}=graph();
    expect(canMoveElements([a],pool,elements,{x:0,y:150})).toBe(false);
  });
  it("supports transfers between lanes and rejects drops outside the destination bounds",()=>{
    const {pool,a,b,elements}=graph();a.parent=pool;b.parent=pool;
    const lane={...shape("lane","bpmn:Lane",pool),x:30,y:100,width:570,height:300};
    expect(canMoveElements([a],lane,elements,{x:0,y:150})).toBe(true);
    expect(canMoveElements([a,b],lane,elements,{x:500,y:150})).toBe(false);
  });
  it("does not let a pool become its own descendant or merge message-flow endpoints",()=>{
    const {root,pool,a,b,edge,elements}=graph();a.parent=pool;
    const other={...pool,id:"other",parent:root};b.parent=other;edge.type="bpmn:MessageFlow";
    expect(canMoveElements([a],other,elements,{x:0,y:150})).toBe(false);
    expect(canMoveElements([pool],pool,elements)).toBe(false);
  });
  it("keeps process work inside a participant when the diagram root is a collaboration",()=>{
    const {root,pool,a,b,elements}=graph();root.type="bpmn:Collaboration";a.parent=pool;b.parent=pool;
    expect(canMoveElements([a,b],root,elements,{x:0,y:0})).toBe(false);
  });
});
