import { describe, expect, it } from "vitest";
import CroppingConnectionDocking from "diagram-js/lib/layout/CroppingConnectionDocking";
import { OrthogonalLayout } from "./Routing";
import { shapePath } from "./Renderer";
import { businessObject, type CanvasElement, type Registry } from "./types";

const shape = (type:string,x:number,y:number,width:number,height:number):CanvasElement => ({id:type,type:"bpmn:"+type,x,y,width,height,businessObject:businessObject("bpmn:"+type)});
const line = (source:CanvasElement,target:CanvasElement,points?:CanvasElement["waypoints"]):CanvasElement => ({...shape("SequenceFlow",0,0,0,0),source,target,waypoints:points});
const docking = new CroppingConnectionDocking({} as ConstructorParameters<typeof CroppingConnectionDocking>[0],{
  getShapePath:shapePath,
  getConnectionPath:(connection:CanvasElement)=>connection.waypoints!.map((p,i)=>(i?"L":"M")+p.x+","+p.y).join("")
} as unknown as ConstructorParameters<typeof CroppingConnectionDocking>[1]);

describe("connection geometry",()=>{
  it("routes a new connector around an intervening activity",()=>{
    const source=shape("Task",0,100,100,80),target=shape("Task",400,100,100,80),obstacle=shape("Task",200,100,100,80);
    const router=new OrthogonalLayout({getAll:()=>[source,target,obstacle]} as Registry);
    const points=router.layoutConnection(line(source,target));
    expect(points.length).toBeGreaterThan(2);
    expect(points.some(p=>p.y<100||p.y>180)).toBe(true);
    for(let i=1;i<points.length;i++){const a=points[i-1],b=points[i];if(Math.abs(a.y-b.y)<.01&&a.y>100&&a.y<180)expect(Math.max(a.x,b.x)<=200||Math.min(a.x,b.x)>=300).toBe(true);}
  });
  it.each([[350,100],[100,350],[-300,100],[100,-300],[265,110],[400,260]])("docks an orthogonal route between activities at %i,%i",(x,y)=>{
    const source=shape("Task",100,100,160,88),target=shape("Task",x,y,160,88),connection=line(source,target);
    connection.waypoints=new OrthogonalLayout().layoutConnection(connection);
    const points=docking.getCroppedWaypoints(connection,source,target);
    for(let i=1;i<points.length;i++)expect(Math.abs(points[i].x-points[i-1].x)<.02||Math.abs(points[i].y-points[i-1].y)<.02).toBe(true);
    for(const [point,node] of [[points[0],source],[points.at(-1)!,target]] as const){
      expect(point.x>=node.x-.1&&point.x<=node.x+node.width+.1&&point.y>=node.y-.1&&point.y<=node.y+node.height+.1).toBe(true);
      expect(Math.min(Math.abs(point.x-node.x),Math.abs(point.x-node.x-node.width),Math.abs(point.y-node.y),Math.abs(point.y-node.y-node.height))).toBeLessThan(1);
    }
  });
  it("uses preview hint endpoints when the preview has no graph endpoints yet",()=>{
    const source=shape("Task",100,100,160,88),target=shape("Task",400,200,160,88);
    expect(new OrthogonalLayout().layoutConnection(line(source,target),{source,target})).toEqual(new OrthogonalLayout().layoutConnection({...line(source,target),source:undefined,target:undefined},{source,target}));
  });
  it("crops a manually edited endpoint from the task centre back to its border",()=>{
    const source=shape("StartEvent",40,100,36,36),target=shape("Task",250,100,160,88);
    const points=docking.getCroppedWaypoints(line(source,target,[{x:58,y:118},{x:160,y:118},{x:160,y:270},{x:330,y:270},{x:330,y:144}]),source,target);
    expect(points.at(-1)!.x).toBeCloseTo(330,1);expect(points.at(-1)!.y).toBeCloseTo(188,1);
    expect(points[0].x).toBeCloseTo(76,1);
  });
  it("docks to a diamond outline instead of the gateway bounding rectangle",()=>{
    const source=shape("Task",0,0,100,80),target=shape("ExclusiveGateway",250,100,50,50);
    const points=docking.getCroppedWaypoints(line(source,target,[{x:50,y:40},{x:275,y:40},{x:275,y:125}]),source,target);
    const end=points.at(-1)!;expect(Math.abs(end.x-275)/25+Math.abs(end.y-125)/25).toBeCloseTo(1,2);
  });
});
