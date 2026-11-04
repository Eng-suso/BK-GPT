import { MoreHorizontal, Plus, Trash2, X, ChevronDown, PanelTopOpen, PanelBottomOpen } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CanvasToolButton, CanvasToolGroup } from "@/components/canvas/CanvasTools";
import { Button } from "@/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuSeparator } from "@/ui/dropdown-menu";
import { BpmnToolIcon } from "./BpmnToolIcon";
import { useRef, useState, type ReactNode, type RefObject } from "react";
import type { CreationTool } from "../bpmn/elements";
import type { SelectionItem } from "../bpmn/useBpmnCanvasUi";
import { Popover, PopoverContent, PopoverTrigger } from "@/ui/popover";
import { BpmnSelectionSummary } from "./BpmnSelectionSummary";
import { useSelectionToolbarPosition } from "./useSelectionToolbarPosition";
import { BpmnTypeOptions } from "./BpmnTypeOptions";

type Props = { host:RefObject<HTMLDivElement|null>; geometryKey:string; actions:CreationTool[]; count:number; name?:string; multiple:boolean; items:SelectionItem[]; onSelect:(id:string)=>unknown; onClear:()=>void; onAction:(id:string,event:Event)=>void };

/** Frequent actions stay local; secondary operations share one disclosure. */
export function BpmnSelectionActions({ host, geometryKey, actions, count, multiple, items, onSelect, onClear, onAction }:Props) {
  const { t } = useTranslation("process");
  const actionTaken = useRef(false);
  const [selectionOpen, setSelectionOpen] = useState(false);
  const enabled = count > 0 && actions.length > 0;
  const {ref,position} = useSelectionToolbarPosition(host,geometryKey,count === 1 ? items[0]?.id : undefined,enabled);
  if (!enabled) return null;
  const append = actions.filter(action=>action.id.startsWith("append."));
  const insert = actions.filter(action=>action.id === "lane.add-above" || action.id === "lane.add-below");
  const replacements = actions.filter(action=>action.id.startsWith("replace."));
  const destructive=actions.filter(action=>action.id === "delete");
  const secondary = actions.filter(action=>action.id !== "delete" && !action.id.startsWith("append.") && !action.id.startsWith("replace.") && !insert.includes(action) && !["connect","replace"].includes(action.id));
  const item = (action:CreationTool) => <DropdownMenuItem key={action.id} onSelect={event=>{actionTaken.current=true;onAction(action.id,event);}} className={action.id === "delete" ? "text-destructive" : undefined}><BpmnToolIcon id={action.id}/>{action.title}</DropdownMenuItem>;
  const closeMenu = (event:Event) => {if(actionTaken.current){event.preventDefault();actionTaken.current=false;host.current?.querySelector<SVGSVGElement>(".djs-container > svg")?.focus();}};
  const menu = (label:string,icon:ReactNode,children:ReactNode) => <DropdownMenu><DropdownMenuTrigger asChild><CanvasToolButton label={label}>{icon}</CanvasToolButton></DropdownMenuTrigger><DropdownMenuContent tabIndex={0} align="start" onCloseAutoFocus={closeMenu}>{children}</DropdownMenuContent></DropdownMenu>;
  return <div ref={ref} className="process-selection-actions" style={position}><CanvasToolGroup label={t("canvas.interactions.selectionActions")}>
    {multiple ? <>
      <Popover open={selectionOpen} onOpenChange={setSelectionOpen}><PopoverTrigger asChild><Button variant="ghost" className="min-h-11 gap-2" aria-label={t("canvas.interactions.selectionCount",{count})}>{t("canvas.interactions.selectionCount",{count})}<ChevronDown aria-hidden className="size-4"/></Button></PopoverTrigger><PopoverContent align="start" className="process-selection-popover" aria-label={t("canvas.interactions.selectionCount",{count})} onCloseAutoFocus={closeMenu}><BpmnSelectionSummary items={items} onSelect={id=>{actionTaken.current=true;setSelectionOpen(false);onSelect(id);}}/></PopoverContent></Popover>
      {actions.some(action=>action.id === "delete") && <CanvasToolButton label={t("canvas.interactions.deleteSelection")} onClick={event=>onAction("delete",event.nativeEvent)}><Trash2 aria-hidden/></CanvasToolButton>}
      <CanvasToolButton label={t("canvas.interactions.clearSelection")} onClick={onClear}><X aria-hidden/></CanvasToolButton>
    </> : <>
      {replacements.length>0&&menu(t("canvas.interactions.replace"),<><BpmnToolIcon id={replacements.find(action=>action.checked)?.id??"replace"}/><ChevronDown aria-hidden className="size-3"/></>,<BpmnTypeOptions actions={replacements} onAction={(id,event)=>{actionTaken.current=true;onAction(id,event);}}/>)}
      {append.length > 0 && menu(t("canvas.interactions.append"),<Plus aria-hidden/>,append.map(item))}
      {insert.map(action=><CanvasToolButton key={action.id} label={action.title} onClick={event=>onAction(action.id,event.nativeEvent)}>{action.id === "lane.add-above" ? <PanelTopOpen aria-hidden/> : <PanelBottomOpen aria-hidden/>}</CanvasToolButton>)}
      {(secondary.length > 0 || destructive.length > 0) && menu(t("canvas.interactions.more"),<MoreHorizontal aria-hidden/>,<>
        {secondary.map(item)}
        {secondary.length > 0 && destructive.length > 0 && <DropdownMenuSeparator/>}
        {destructive.map(item)}
      </>)}
    </>}
  </CanvasToolGroup></div>;
}
