import type { CanvasElement, Factory, Point, Registry } from "./types";

type Modeling = {
  createShape:(shape:CanvasElement,position:Point,parent:CanvasElement,hints?:Record<string,unknown>)=>CanvasElement;
  resizeShape:(shape:CanvasElement,bounds:{x:number;y:number;width:number;height:number},min?:unknown,hints?:Record<string,unknown>)=>void;
  moveShape:(shape:CanvasElement,delta:Point,parent?:CanvasElement,index?:number,hints?:Record<string,unknown>)=>void;
  removeElements:(elements:CanvasElement[])=>void;
};
export type LaneContext = { element:CanvasElement; action:string; lane?:CanvasElement };

/** Lane changes compose ordinary modeling commands into one reversible action.
 * Removing a responsibility partition keeps its work and existing flow IDs. */
export class LaneCommand {
  static $inject = ["modeling","elementFactory","elementRegistry"];
  constructor(private modeling:Modeling,private factory:Factory,private registry:Registry) {}
  execute() { return []; }
  revert() { return []; }
  preExecute({element,action,lane:adopted}:LaneContext) {
    const parent = element.type === "bpmn:Lane" ? element.parent! : element;
    if (!parent || !/Participant$|Lane$/.test(parent.type)) return;
    const lanes = (parent.children ?? []).filter(child=>child.type === "bpmn:Lane" && child !== adopted).sort((a,b)=>a.y-b.y);
    const box = (shape:CanvasElement,overrides:Partial<CanvasElement>) => this.modeling.resizeShape(shape,{x:shape.x,y:shape.y,width:shape.width,height:shape.height,...overrides},undefined,{delirLanes:true});
    const move = (shape:CanvasElement,delta:Point,target?:CanvasElement) => this.modeling.moveShape(shape,delta,target,undefined,{delirLanes:true});
    const newLane = (y:number,height:number) => {
      const shape=this.factory.createShape({type:"bpmn:Lane",width:parent.width-30,height});
      return this.modeling.createShape(shape,{x:parent.x+30+shape.width/2,y:y+height/2},parent,{delirLanes:true});
    };
    const assign = (partition:CanvasElement) => {
      for(const child of [...(parent.children ?? [])]) {
        if(child === partition || child.type === "bpmn:Lane" || child.labelTarget || child.waypoints) continue;
        const center=child.y+child.height/2;
        if(center>=partition.y && center<=partition.y+partition.height) move(child,{x:0,y:0},partition);
      }
    };
    if(action === "remove") {
      if(element.type !== "bpmn:Lane") return;
      const index=lanes.indexOf(element), neighbor=lanes[index-1] ?? lanes[index+1];
      const low=Math.min(element.y,neighbor?.y ?? element.y), high=Math.max(element.y+element.height,neighbor ? neighbor.y+neighbor.height : element.y+element.height);
      if(neighbor) box(neighbor,{y:low,height:high-low});
      const target=neighbor ?? parent;
      const transfer=(partition:CanvasElement)=>{for(const child of [...(partition.children??[])]) {if(child.type === "bpmn:Lane")transfer(child);else if(!child.labelTarget && !child.waypoints)move(child,{x:0,y:0},target);}};
      transfer(element);this.modeling.removeElements([element]);return;
    }
    if(action.startsWith("split")) {
      const count=action === "split-3" ? 3 : 2;
      const owner=element.type === "bpmn:Lane" ? element : parent;
      if((owner.children??[]).some(child=>child.type === "bpmn:Lane"))return;
      const height=owner.height/count;
      // Split a leaf lane as sibling partitions; split a pool into its lanes.
      if(element.type === "bpmn:Lane") {
        const contents=[...(element.children??[])].filter(child=>!child.labelTarget&&!child.waypoints);
        const partitions=[element];
        box(element,{height});
        for(let i=1;i<count;i++) {
          const next=newLane(element.y+i*height,height);
          partitions.push(next);
        }
        for(const child of contents) {
          const partition=partitions[Math.min(count-1,Math.max(0,Math.floor((child.y+child.height/2-element.y)/height)))];
          if(partition!==element)move(child,{x:0,y:0},partition);
        }
      } else for(let i=0;i<count;i++)assign(newLane(parent.y+i*height,height));
      return;
    }
    if(!lanes.length) {
      const first=adopted ?? newLane(parent.y,parent.height);
      box(first,{x:parent.x+30,y:parent.y,width:parent.width-30,height:parent.height});assign(first);
      if(adopted)return;
      lanes.push(first);
    }
    const selected=element.type === "bpmn:Lane" ? lanes.indexOf(element) : lanes.length-1;
    const index=action === "add-above" ? Math.max(0,selected) : selected+1;
    const y=lanes[index]?.y ?? parent.y+parent.height;
    const height=144, oldBottom=parent.y+parent.height;
    box(parent,{height:parent.height+height});
    // Keep other participants below this pool clear of its new extent.
    if(parent.type === "bpmn:Participant") for(const pool of this.registry.getAll())if(pool.type === "bpmn:Participant"&&pool!==parent&&pool.y>=oldBottom)move(pool,{x:0,y:height});
    for(const partition of lanes.slice(index))move(partition,{x:0,y:height});
    const created=adopted ?? newLane(y,height);
    box(created,{x:parent.x+30,y,width:parent.width-30,height});
  }
}
