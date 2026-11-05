import {expect,it} from "vitest";
import {ConnectionOrder} from "./ConnectionOrder";
import {businessObject,type CanvasElement,type Bus,type Registry} from "./types";

it("keeps links above pool backgrounds without changing containment or replacing DOM nodes",()=>{
  const element=(id:string,type:string):CanvasElement=>({id,type:"bpmn:"+type,x:0,y:0,width:100,height:100,businessObject:businessObject("bpmn:"+type,{id})});
  const link={...element("link","Association"),waypoints:[{x:0,y:0},{x:100,y:100}]},pool=element("pool","Participant"),note=element("note","TextAnnotation"),root=element("root","Collaboration");
  root.children=[link,pool,note];for(const child of root.children)child.parent=root;
  const layer=document.createElementNS("http://www.w3.org/2000/svg","g"),graphics=new Map<string,SVGElement>();
  for(const child of root.children){const group=document.createElementNS("http://www.w3.org/2000/svg","g"),gfx=document.createElementNS("http://www.w3.org/2000/svg","g");group.setAttribute("data-id",child.id);group.append(gfx);layer.append(group);graphics.set(child.id,gfx);}
  let arrange=()=>{};
  const bus={on:(_events:unknown,_priority:unknown,callback:()=>void)=>{arrange=callback;}} as Bus;
  new ConnectionOrder(bus,{getAll:()=>[root,...root.children!],getGraphics:(element:CanvasElement)=>graphics.get(element.id)!} as Registry);
  arrange();expect(Array.from(layer.children).map(group=>group.getAttribute("data-id"))).toEqual(["pool","link","note"]);
  expect(root.children.map(child=>child.id)).toEqual(["link","pool","note"]);expect(graphics.get("link")!.parentElement).toBe(layer.children[1]);
  const observer=new MutationObserver(()=>{});observer.observe(layer,{childList:true});arrange();expect(observer.takeRecords()).toEqual([]);observer.disconnect();
  layer.insertBefore(graphics.get("link")!.parentElement!,layer.firstChild);arrange();expect(layer.children[0].getAttribute("data-id")).toBe("pool");
  const lane=element("lane","Lane"),laneGroup=document.createElementNS("http://www.w3.org/2000/svg","g"),laneGraphics=document.createElementNS("http://www.w3.org/2000/svg","g");laneGroup.setAttribute("data-id","lane");laneGroup.append(laneGraphics);graphics.set("lane",laneGraphics);layer.prepend(laneGroup);
  root.children=[lane,pool,note];lane.parent=root;
  arrange();expect(Array.from(layer.children).map(group=>group.getAttribute("data-id")).slice(0,3)).toEqual(["pool","lane","note"]);
  observer.observe(layer,{childList:true});arrange();expect(observer.takeRecords()).toEqual([]);observer.disconnect();
});
