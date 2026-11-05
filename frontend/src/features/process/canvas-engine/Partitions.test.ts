import {describe,expect,it} from "vitest";
import {partitionResize,validPartitionResize} from "./Partitions";
import {businessObject,type CanvasElement} from "./types";

function fixture() {
  const element=(id:string,type:string,x:number,y:number,width:number,height:number,parent?:CanvasElement):CanvasElement=>{
    const shape={id,type:"bpmn:"+type,x,y,width,height,parent,children:[],businessObject:businessObject("bpmn:"+type,{id})};
    parent?.children?.push(shape);return shape;
  };
  const pool=element("pool","Participant",100,100,800,400);
  const a=element("a","Lane",130,100,770,200,pool),b=element("b","Lane",130,300,770,200,pool);
  const task=element("task","Task",230,350,160,88,b);
  return{element,pool,a,b,task};
}
describe("BPMN partition geometry",()=>{
  it("grows the last band and the full width without adding container padding",()=>{
    const{pool,a,b}=fixture();const plan=partitionResize(pool,{x:100,y:100,width:900,height:500});
    expect(plan.get(a)).toEqual({x:130,y:100,width:870,height:200});
    expect(plan.get(b)).toEqual({x:130,y:300,width:870,height:300});expect(validPartitionResize(plan)).toBe(true);
  });
  it("shares a divider with the next band while retaining the pool extent",()=>{
    const{pool,a,b}=fixture();const plan=partitionResize(a,{x:130,y:100,width:770,height:230});
    expect(plan.get(pool)).toMatchObject({y:100,height:400});expect(plan.get(b)).toMatchObject({y:330,height:170});expect(validPartitionResize(plan)).toBe(true);
  });
  it("resizes the whole pool horizontally when a lane edge is dragged",()=>{
    const{pool,a,b}=fixture();const plan=partitionResize(b,{x:110,y:300,width:890,height:240});
    expect(plan.get(pool)).toEqual({x:80,y:100,width:920,height:440});expect(plan.get(a)).toMatchObject({x:110,width:890});
  });
  it("rejects a divider through an activity and a collapsed sibling",()=>{
    const{a}=fixture();expect(validPartitionResize(partitionResize(a,{x:130,y:100,width:770,height:300}))).toBe(false);
    expect(validPartitionResize(partitionResize(a,{x:130,y:100,width:770,height:370}))).toBe(false);
  });
  it("repairs inset lanes on the next edit without mutating the source objects",()=>{
    const{pool,a,b}=fixture();a.y=120;a.height=180;b.width=730;b.height=160;
    const plan=partitionResize(pool,{x:100,y:100,width:800,height:440});
    expect(plan.get(a)).toEqual({x:130,y:100,width:770,height:200});expect(plan.get(b)).toEqual({x:130,y:300,width:770,height:240});expect(a.y).toBe(120);
  });
  it("tiles nested lanes when an outer pool changes width and height",()=>{
    const{element,pool,b}=fixture();b.children=[];const nested=element("nested","Lane",160,300,740,200,b);
    expect(partitionResize(pool,{x:100,y:100,width:900,height:500}).get(nested)).toEqual({x:160,y:300,width:840,height:300});
  });
  it("handles process lanes without fabricating a participant",()=>{
    const{pool,a,b}=fixture();pool.type="bpmn:Process";const plan=partitionResize(b,{x:130,y:300,width:870,height:250});
    expect(plan.has(pool)).toBe(false);expect(plan.get(a)).toMatchObject({x:130,width:870});expect(plan.get(b)).toMatchObject({y:300,height:250});
  });
});
