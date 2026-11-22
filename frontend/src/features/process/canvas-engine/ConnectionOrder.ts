import type {Bus,CanvasElement,Registry} from "./types";

const rank=(element:CanvasElement)=>element.type === "bpmn:Participant" ? 0 : element.type === "bpmn:Lane" ? 1 : element.waypoints ? 2 : 3;

/** Paint container backgrounds before links. Semantic containment and XML order
 * stay unchanged; cross-pool links must not disappear under a participant. */
export class ConnectionOrder {
  static $inject=["eventBus","elementRegistry"];
  constructor(bus:Bus,registry:Registry) {
    const arrange=()=>{
      for(const owner of registry.getAll()) {
        const children=owner.children??[];
        if(!children.some(child=>/Participant$|Lane$/.test(child.type)))continue;
        const groups=[...children].sort((a,b)=>rank(a)-rank(b)).map(child=>registry.getGraphics(child)?.parentElement).filter((group):group is HTMLElement=>Boolean(group));
        const container=groups[0]?.parentElement;
        if(!container)continue;
        let expected=container.firstElementChild;
        for(const group of groups) {
          if(group===expected)expected=expected.nextElementSibling;
          else container.insertBefore(group,expected);
        }
      }
    };
    bus.on(["import.done","elements.changed"],500,arrange);
  }
}
