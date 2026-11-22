import type { CanvasElement, Point } from "./types";
import { flowScope } from "./connectionRules";

/** Small bounded detours for new connectors. User-edited paths are never reset. */
export function avoidObstacles(points: Point[], source: CanvasElement, target: CanvasElement, elements: CanvasElement[], type: string): Point[] {
  const obstacles=elements.filter(el=>el!==source&&el!==target&&!el.labelTarget&&!el.waypoints&&/Task$|Activity$|Event$|Gateway$|DataObjectReference$|DataStoreReference$/.test(el.type));
  const intersects=(a:Point,b:Point,el:CanvasElement)=>{
    const left=el.x-6,right=el.x+el.width+6,top=el.y-6,bottom=el.y+el.height+6;
    return Math.abs(a.x-b.x)<.01 ? a.x>left&&a.x<right&&Math.max(a.y,b.y)>top&&Math.min(a.y,b.y)<bottom
      : Math.abs(a.y-b.y)<.01 ? a.y>top&&a.y<bottom&&Math.max(a.x,b.x)>left&&Math.min(a.x,b.x)<right : true;
  };
  const hits=(route:Point[])=>obstacles.some(obstacle=>route.slice(1).some((end,index)=>intersects(route[index],end,obstacle)));
  if(!hits(points))return points;
  const start=points[0],end=points.at(-1)!;
  const horizontal=Math.abs(start.x-end.x)>=Math.abs(start.y-end.y);
  const scope=type === "bpmn:SequenceFlow" ? flowScope(source.parent) : undefined;
  const bounded=scope && /Participant$|SubProcess$/.test(scope.type) ? scope : null;
  const channels=[...new Set(obstacles.flatMap(el=>horizontal?[el.y-16,el.y+el.height+16]:[el.x-16,el.x+el.width+16]))]
    .filter(value=>!bounded||(horizontal ? value>bounded.y+8&&value<bounded.y+bounded.height-8 : value>bounded.x+38&&value<bounded.x+bounded.width-8))
    .sort((a,b)=>Math.abs(a-(horizontal?(start.y+end.y)/2:(start.x+end.x)/2))-Math.abs(b-(horizontal?(start.y+end.y)/2:(start.x+end.x)/2))).slice(0,16);
  for(const channel of channels){
    const direction=horizontal?(end.x>=start.x?1:-1):(end.y>=start.y?1:-1),stub=12*direction;
    const route=horizontal?[start,{x:start.x+stub,y:start.y},{x:start.x+stub,y:channel},{x:end.x-stub,y:channel},{x:end.x-stub,y:end.y},end]
      :[start,{x:start.x,y:start.y+stub},{x:channel,y:start.y+stub},{x:channel,y:end.y-stub},{x:end.x,y:end.y-stub},end];
    // A detour must also clear the source and target interiors.
    const interior=route.slice(1,-1);
    const crossesEndpoint=[source,target].some(el=>interior.slice(1).some((p,i)=>intersects(interior[i],p,{...el,x:el.x+8,y:el.y+8,width:el.width-16,height:el.height-16})));
    if(!crossesEndpoint&&!hits(route))return route;
  }
  return points;
}
