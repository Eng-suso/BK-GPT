import type { CanvasElement, Registry } from "./types";

export function deletionTargets(elements:CanvasElement[],registry:Registry) {
  return [...new Map(elements.map(element=>element.labelTarget ?? element).map(element=>[element.id,element])).values()]
    .filter(element=>registry.get(element.id)===element && !/Process$|Collaboration$/.test(element.type));
}

/** One history entry, regardless of selection order. Remove explicitly selected
 * work first; removing responsibility partitions retains the unselected work. */
export class DeleteSelectionCommand {
  static $inject=["modeling","commandStack","elementRegistry"];
  constructor(
    private modeling:{removeElements:(elements:CanvasElement[])=>void},
    private commands:{execute:(name:string,context:unknown)=>void},
    private registry:Registry,
  ) {}
  execute(){return [];}
  revert(){return [];}
  preExecute({elements}:{elements:CanvasElement[]}) {
    const targets=deletionTargets(elements,this.registry);
    const work=targets.filter(element=>element.type!=="bpmn:Lane");
    if(work.length)this.modeling.removeElements(work);
    for(const lane of targets.filter(element=>element.type==="bpmn:Lane")) {
      // A selected pool or outer lane may already have removed this descendant.
      if(this.registry.get(lane.id))this.commands.execute("delir.lanes",{element:lane,action:"remove"});
    }
  }
}
