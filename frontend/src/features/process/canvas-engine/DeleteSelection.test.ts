import {describe,expect,it,vi} from "vitest";
import {deletionTargets,DeleteSelectionCommand} from "./DeleteSelection";
import {businessObject,type CanvasElement,type Registry} from "./types";

const element=(id:string,type="Task"):CanvasElement=>({id,type:"bpmn:"+type,businessObject:businessObject("bpmn:"+type,{id}),x:0,y:0,width:160,height:88});
const registry=(elements:CanvasElement[])=>({get:(id:string)=>elements.find(element=>element.id===id)} as Registry);

describe("canvas deletion selection",()=>{
  it("treats labels as their owner once and excludes roots and stale objects",()=>{
    const task=element("task"),label={...element("label","label"),labelTarget:task},root=element("root","Process"),collaboration=element("collaboration","Collaboration"),stale=element("stale");
    expect(deletionTargets([label,root,task,collaboration,stale,label],registry([task,label,root,collaboration]))).toEqual([task]);
  });
  it("removes explicit work before partitions and skips descendants already removed with a pool",()=>{
    const lane=element("lane","Lane"),task=element("task"),pool=element("pool","Participant"),nested=element("nested","Lane");
    const remaining=[lane,task,pool,nested],calls:string[]=[];
    const modeling={removeElements:vi.fn((elements:CanvasElement[])=>{calls.push("work");for(const item of [...elements,nested])remaining.splice(remaining.indexOf(item),1);})};
    const commands={execute:vi.fn((_name:string,context:unknown)=>{calls.push((context as {element:CanvasElement}).element.id);})};
    new DeleteSelectionCommand(modeling,commands,registry(remaining)).preExecute({elements:[lane,nested,task,pool]});
    expect(modeling.removeElements).toHaveBeenCalledWith([task,pool]);expect(calls).toEqual(["work","lane"]);
    expect(commands.execute).toHaveBeenCalledWith("delir.lanes",{element:lane,action:"remove"});
  });
});
