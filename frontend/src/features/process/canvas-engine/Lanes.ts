import type { CanvasElement, Factory, Point, Registry } from "./types";
import { partitionResize } from "./Partitions";

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
    if (!parent || !/Participant$|Lane$|Process$/.test(parent.type)) return;
    const lanes = (parent.children ?? []).filter(child=>child.type === "bpmn:Lane" && child !== adopted).sort((a,b)=>a.y-b.y);
    // A process can have lanes without a drawn participant. Its root has no bounds.
    const rootLanes = parent.type === "bpmn:Process";
    const envelope = lanes.length ? lanes : adopted ? [adopted] : [];
    if(rootLanes && !envelope.length)return;
    const bounds = rootLanes ? {
      x:Math.min(...envelope.map(lane=>lane.x)),y:Math.min(...envelope.map(lane=>lane.y)),
      width:Math.max(...envelope.map(lane=>lane.x+lane.width))-Math.min(...envelope.map(lane=>lane.x)),
      height:Math.max(...envelope.map(lane=>lane.y+lane.height))-Math.min(...envelope.map(lane=>lane.y)),
    } : {x:parent.x,y:parent.y,width:parent.width,height:parent.height};
    const inset = rootLanes ? 0 : 30;
    const box = (shape:CanvasElement,overrides:Partial<CanvasElement>) => this.modeling.resizeShape(shape,{x:shape.x,y:shape.y,width:shape.width,height:shape.height,...overrides},undefined,{delirLanes:true});
    const move = (shape:CanvasElement,delta:Point,target?:CanvasElement) => this.modeling.moveShape(shape,delta,target,undefined,{delirLanes:true});
    if(lanes.length && !rootLanes)for(const [shape,next] of partitionResize(parent,bounds,parent,adopted)) {
      if(shape===adopted)continue;
      if(shape.x!==next.x||shape.y!==next.y||shape.width!==next.width||shape.height!==next.height)box(shape,next);
    }
    const newLane = (y:number,height:number) => {
      const shape=this.factory.createShape({type:"bpmn:Lane",width:bounds.width-inset,height});
      return this.modeling.createShape(shape,{x:bounds.x+inset+shape.width/2,y:y+height/2},parent,{delirLanes:true});
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
      const oldHeight=owner.height,oldBottom=owner.y+oldHeight;
      const contents=[...(owner.children??[])].filter(child=>!child.labelTarget&&!child.waypoints);
      const placements=contents.map(child=>{
        const labels=this.registry.getAll().filter(label=>label.labelTarget===child);
        return {child,index:Math.min(count-1,Math.max(0,Math.floor((child.y+child.height/2-owner.y)/(oldHeight/count)))),
          top:Math.min(0,...labels.map(label=>label.y-child.y)),
          bottom:Math.max(child.height,...labels.map(label=>label.y+label.height-child.y))};
      });
      const height=Math.max(oldHeight/count,80,...placements.map(item=>item.bottom-item.top+24));
      const growth=height*count-oldHeight;
      if(growth>0) {
        const oldParentBottom=rootLanes ? bounds.y+bounds.height : parent.y+parent.height;
        if(!rootLanes)box(parent,{height:parent.height+growth});
        for(const sibling of lanes)if(sibling!==element&&sibling.y>=oldBottom)move(sibling,{x:0,y:growth});
        if(parent.type === "bpmn:Participant")for(const pool of this.registry.getAll())if(pool.type === "bpmn:Participant"&&pool!==parent&&pool.y>=oldParentBottom)move(pool,{x:0,y:growth});
      }
      const partitions:CanvasElement[]=[];
      if(element.type === "bpmn:Lane") {box(element,{height});partitions.push(element);}
      for(let i=partitions.length;i<count;i++)partitions.push(newLane(owner.y+i*height,height));
      for(const {child,index,top,bottom} of placements) {
        const target=partitions[index];
        const y=Math.max(target.y+12-top,Math.min(target.y+height-12-bottom,child.y));
        if(child.parent!==target || y!==child.y)move(child,{x:0,y:y-child.y},target);
      }
      return;
    }
    if(!lanes.length) {
      const first=adopted ?? newLane(bounds.y,bounds.height);
      box(first,{x:bounds.x+inset,y:bounds.y,width:bounds.width-inset,height:bounds.height});assign(first);
      if(adopted)return;
      lanes.push(first);
    }
    const selected=element.type === "bpmn:Lane" ? lanes.indexOf(element) : lanes.length-1;
    const index=action === "add-above" ? Math.max(0,selected) : selected+1;
    const y=lanes[index]?.y ?? bounds.y+bounds.height;
    const height=144, oldBottom=bounds.y+bounds.height;
    if(!rootLanes)box(parent,{height:parent.height+height});
    // Keep other participants below this pool clear of its new extent.
    if(parent.type === "bpmn:Participant") for(const pool of this.registry.getAll())if(pool.type === "bpmn:Participant"&&pool!==parent&&pool.y>=oldBottom)move(pool,{x:0,y:height});
    for(const partition of lanes.slice(index))move(partition,{x:0,y:height});
    const created=adopted ?? newLane(y,height);
    box(created,{x:bounds.x+inset,y,width:bounds.width-inset,height});
  }
}
