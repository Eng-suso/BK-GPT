import type { RefObject } from "react";
import { useTranslation } from "react-i18next";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuSeparator, DropdownMenuSub, DropdownMenuSubTrigger, DropdownMenuSubContent } from "@/ui/dropdown-menu";
import type { CreationTool } from "../bpmn/elements";
import type { CanvasContextPoint } from "../bpmn/canvasInteractions";
import { BpmnToolIcon } from "./BpmnToolIcon";
import { BpmnTypeOptions } from "./BpmnTypeOptions";

type Props = {
  point:CanvasContextPoint|null; host:RefObject<HTMLDivElement|null>; actions:CreationTool[];
  canUndo:boolean; canRedo:boolean; canSelectAll:boolean;
  onClose:()=>void; onUndo:()=>void; onRedo:()=>void;
  onAction:(id:string,event:Event)=>void; onCreate:(event:Event)=>void;
};

/** Uses the same model commands as the local selection controls. */
export function BpmnCanvasContextMenu({point,host,actions,canUndo,canRedo,canSelectAll,onClose,onUndo,onRedo,onAction,onCreate}:Props) {
  const {t,i18n}=useTranslation("process");
  if(!point)return null;
  const mouseEvent=()=>new MouseEvent("click",{clientX:point.x,clientY:point.y,bubbles:true});
  const run=(id:string)=>{onClose();onAction(id,mouseEvent());};
  const append=actions.filter(action=>action.id.startsWith("append."));
  const replace=actions.filter(action=>action.id.startsWith("replace."));
  const rest=actions.filter(action=>!action.id.startsWith("append.")&&!action.id.startsWith("replace.")&&action.id!=="delete");
  const item=(action:CreationTool)=><DropdownMenuItem key={action.id} onSelect={()=>run(action.id)}><BpmnToolIcon id={action.id}/>{action.title}</DropdownMenuItem>;
  return <DropdownMenu open onOpenChange={open=>{if(!open)onClose();}} modal={false}>
    <DropdownMenuTrigger asChild><span aria-hidden="true" className="pointer-events-none fixed size-px opacity-0" style={{left:point.x,top:point.y}}/></DropdownMenuTrigger>
    <DropdownMenuContent tabIndex={0} align="start" sideOffset={2} aria-label={t("canvas.interactions.selectionActions")} onCloseAutoFocus={event=>{event.preventDefault();host.current?.querySelector<SVGSVGElement>(".djs-container > svg")?.focus();}}>
      {replace.length>0&&<><BpmnTypeOptions actions={replace} onAction={id=>run(id)}/><DropdownMenuSeparator/></>}
      <DropdownMenuItem disabled={!canUndo} onSelect={()=>{onClose();onUndo();}}>{t("canvas.interactions.undo")}</DropdownMenuItem>
      <DropdownMenuItem disabled={!canRedo} onSelect={()=>{onClose();onRedo();}}>{t("canvas.interactions.redo")}</DropdownMenuItem>
      <DropdownMenuSeparator/>
      {actions.length ? <>
        {rest.map(item)}
        {append.length>0&&<DropdownMenuSub><DropdownMenuSubTrigger>{t("canvas.interactions.append")}</DropdownMenuSubTrigger><DropdownMenuSubContent>{append.map(item)}</DropdownMenuSubContent></DropdownMenuSub>}
        {actions.some(action=>action.id==="delete")&&<><DropdownMenuSeparator/><DropdownMenuItem className="text-destructive" onSelect={()=>run("delete")}><BpmnToolIcon id="delete"/>{actions.find(action=>action.id==="delete")!.title}</DropdownMenuItem></>}
      </> : <DropdownMenuItem onSelect={()=>{onClose();onCreate(mouseEvent());}}>{t("canvas.tools.create.task")}</DropdownMenuItem>}
      {i18n.exists("canvas.contextMenu.selectAll",{ns:"process"}) && <><DropdownMenuSeparator/>
      <DropdownMenuItem disabled={!canSelectAll} onSelect={()=>run("select-all")}>{t("canvas.contextMenu.selectAll")}</DropdownMenuItem></>}
    </DropdownMenuContent>
  </DropdownMenu>;
}
