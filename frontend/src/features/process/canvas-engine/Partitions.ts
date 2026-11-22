import type { CanvasElement } from "./types";

export type Bounds = { x:number; y:number; width:number; height:number };
export const laneChildren = (owner:CanvasElement) => (owner.children ?? []).filter(child=>child.type === "bpmn:Lane").sort((a,b)=>a.y-b.y);
const bounds = ({x,y,width,height}:Bounds):Bounds => ({x,y,width,height});
const bottom = (box:Bounds) => box.y+box.height;
export const laneInset = (owner:CanvasElement) => owner.type === "bpmn:Participant" || owner.type === "bpmn:Lane" ? 30 : 0;

/** Partition geometry, independent of SVG and XML. Internal dividers keep their
 * position; outer edges belong to the containing pool (or parent lane). */
export function partitionResize(shape:CanvasElement, requested:Bounds, previous:Bounds=shape, excluded?:CanvasElement) {
  const changes = new Map<CanvasElement,Bounds>();
  const children=(owner:CanvasElement)=>laneChildren(owner).filter(lane=>lane!==excluded);
  const read = (element:CanvasElement) => changes.get(element) ?? bounds(element);
  function resize(element:CanvasElement, next:Bounds, old:Bounds) {
    changes.set(element,bounds(next));
    const parent=element.parent;
    if(element.type === "bpmn:Lane" && parent && /Participant$|Lane$|Process$/.test(parent.type)) {
      const siblings=children(parent),index=siblings.indexOf(element);
      const before=siblings[index-1],after=siblings[index+1];
      if(after && bottom(next)!==bottom(old)) changes.set(after,{...read(after),y:bottom(next),height:bottom(read(after))-bottom(next)});
      if(before && next.y!==old.y) changes.set(before,{...read(before),height:next.y-read(before).y});
      if(parent.type !== "bpmn:Process") {
        const parentBox=read(parent),left=next.x-laneInset(parent),right=next.x+next.width;
        const top=index===0 ? next.y : parentBox.y,end=index===siblings.length-1 ? bottom(next) : bottom(parentBox);
        resize(parent,{x:left,y:top,width:right-left,height:end-top},parentBox);
      }
    }
  }
  resize(shape,requested,previous);
  // Retile top-down. This also repairs pre-existing inset/gapped layouts when
  // the user next edits a container; loading alone never rewrites their XML.
  function tile(owner:CanvasElement) {
    const lanes=children(owner);if(!lanes.length)return;
    const ownerBox=read(owner),inset=laneInset(owner);
    const root=owner.type === "bpmn:Process";
    const area=root ? {
      x:Math.min(...lanes.map(lane=>read(lane).x)),y:Math.min(...lanes.map(lane=>read(lane).y)),
      width:Math.max(...lanes.map(lane=>read(lane).x+read(lane).width))-Math.min(...lanes.map(lane=>read(lane).x)),
      height:Math.max(...lanes.map(lane=>bottom(read(lane))))-Math.min(...lanes.map(lane=>read(lane).y)),
    } : ownerBox;
    const dividers=[area.y,...lanes.slice(1).map(lane=>read(lane).y),bottom(area)];
    lanes.forEach((lane,index)=>{changes.set(lane,{x:area.x+inset,y:dividers[index],width:area.width-inset,height:dividers[index+1]-dividers[index]});tile(lane);});
  }
  let owner=shape;
  while(owner.type === "bpmn:Lane" && owner.parent && /Participant$|Lane$|Process$/.test(owner.parent.type))owner=owner.parent;
  tile(owner);
  return changes;
}

/** Reject a divider crossing its neighbor or cutting through existing work. */
export function validPartitionResize(changes:Map<CanvasElement,Bounds>) {
  for(const [element,box] of changes) {
    if(box.width<100 || box.height<60)return false;
    for(const child of element.children ?? []) {
      if(child.waypoints || child.type === "bpmn:Lane" || child.labelTarget)continue;
      const content=changes.get(child) ?? child;
      if(content.x<box.x+laneInset(element)+8 || content.y<box.y+8 || content.x+content.width>box.x+box.width-8 || bottom(content)>bottom(box)-8)return false;
      for(const label of child.children ?? [])if(label.labelTarget===child && (label.y<box.y || bottom(label)>bottom(box)))return false;
    }
  }
  return true;
}
