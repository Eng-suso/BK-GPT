import {ArrowUpRight,Hand,MousePointer2,Scan,UnfoldHorizontal,Trash2,Settings2} from "lucide-react";
import {bpmnIconClass} from "../bpmn/iconClass";
import "bpmn-font/dist/css/bpmn.css";

/** Standard BPMN symbols; DeliR owns the menu and canvas interaction. */
export function BpmnToolIcon({id}:{id:string}) {
  const symbol=bpmnIconClass(id);
  if(symbol)return <span aria-hidden="true" data-bpmn-symbol={symbol} className={symbol+" inline-flex size-5 shrink-0 items-center justify-center text-xl leading-none"}/>;
  if(id==="select")return <MousePointer2 aria-hidden/>;
  if(id==="hand-tool")return <Hand aria-hidden/>;
  if(id==="lasso-tool")return <Scan aria-hidden/>;
  if(id==="space-tool")return <UnfoldHorizontal aria-hidden/>;
  if(/sequence-flow|message-flow|association/.test(id))return <svg aria-hidden="true" viewBox="0 0 24 24" className="size-5 shrink-0" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M3 12h17m-5-5 5 5-5 5" strokeDasharray={/message|association/.test(id)?"3 2":undefined}/>{/message/.test(id)&&<circle cx="3" cy="12" r="2" fill="var(--color-surface-primary)"/>}</svg>;
  if(/connect/.test(id))return <ArrowUpRight aria-hidden/>;
  if(/delete|remove/.test(id))return <Trash2 aria-hidden/>;
  return <Settings2 aria-hidden/>;
}
