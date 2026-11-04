import { MoreHorizontal, Plus, ArrowUpRight, Settings2, Trash2, X, ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CanvasToolButton, CanvasToolGroup } from "@/components/canvas/CanvasTools";
import { Button } from "@/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/ui/dropdown-menu";
import { BpmnToolIcon } from "./BpmnToolIcon";
import { useRef, useState, type ReactNode } from "react";
import type { CreationTool } from "../bpmn/elements";
import type { SelectionItem } from "../bpmn/useBpmnCanvasUi";
import { Popover, PopoverContent, PopoverTrigger } from "@/ui/popover";
import { BpmnSelectionSummary } from "./BpmnSelectionSummary";

/** Uses only actions offered by the existing BPMN context-pad provider. */
export function BpmnSelectionActions({ actions, count, name, multiple, items, onSelect, onClear, onAction }: { actions: CreationTool[]; count: number; name?: string; multiple: boolean; items: SelectionItem[]; onSelect: (id: string) => unknown; onClear: () => void; onAction: (id: string, event: Event) => void }) {
  const { t } = useTranslation("process");
  const actionTaken = useRef(false);
  const [selectionOpen, setSelectionOpen] = useState(false);
  if (!count || !actions.length) return null;
  const append = actions.filter(action => action.id.startsWith("append."));
  const lanes = actions.filter(action => action.id.startsWith("lane."));
  const replacements = actions.filter(action => action.id.startsWith("replace."));
  const remaining = actions.filter(action => !action.id.startsWith("append.") && !action.id.startsWith("replace.") && !action.id.startsWith("lane.") && !["connect", "replace"].includes(action.id));
  const menu = (items: CreationTool[], label: string, icon: ReactNode) => <DropdownMenu><DropdownMenuTrigger asChild><Button variant="ghost" className="min-h-11 gap-2" aria-label={label}>{icon}<span className="process-selection-action-text">{label}</span></Button></DropdownMenuTrigger><DropdownMenuContent align="start" onCloseAutoFocus={event => { if (actionTaken.current) { event.preventDefault(); actionTaken.current = false; } }}>{items.map(action => <DropdownMenuItem key={action.id} onClick={event => { actionTaken.current = true; onAction(action.id, event.nativeEvent); }} className={action.id === "delete" ? "text-destructive" : undefined}><BpmnToolIcon id={action.id} />{action.title}</DropdownMenuItem>)}</DropdownMenuContent></DropdownMenu>;
  return <CanvasToolGroup label={t("canvas.interactions.selectionActions")} className="process-selection-actions">
    {multiple ? <>
      <Popover open={selectionOpen} onOpenChange={setSelectionOpen}><PopoverTrigger asChild><Button variant="ghost" className="min-h-11 gap-2" aria-label={t("canvas.interactions.selectionCount", { count })}>{t("canvas.interactions.selectionCount", { count })}<ChevronDown aria-hidden className="size-4" /></Button></PopoverTrigger><PopoverContent align="start" className="process-selection-popover" aria-label={t("canvas.interactions.selectionCount", { count })} onCloseAutoFocus={event => { if (actionTaken.current) { event.preventDefault(); actionTaken.current = false; } }}><BpmnSelectionSummary items={items} onSelect={id => { actionTaken.current = true; setSelectionOpen(false); onSelect(id); }} /></PopoverContent></Popover>
      {actions.some(action => action.id === "delete") && <CanvasToolButton label={t("canvas.interactions.deleteSelection")} onClick={event => onAction("delete", event.nativeEvent)}><Trash2 aria-hidden /></CanvasToolButton>}
      <CanvasToolButton label={t("canvas.interactions.clearSelection")} onClick={onClear}><X aria-hidden /></CanvasToolButton>
    </> : <>
    <span className="process-selection-label">{name || t("canvas.interactions.selected")}</span>
    {append.length > 0 && menu(append, t("canvas.interactions.append"), <Plus aria-hidden className="size-4" />)}
    {actions.some(action => action.id === "connect") && <CanvasToolButton label={t("canvas.interactions.connect")} onClick={event => onAction("connect", event.nativeEvent)}><ArrowUpRight aria-hidden /></CanvasToolButton>}
    {lanes.length > 0 && menu(lanes, t("canvas.lanes.manage"), <Plus aria-hidden className="size-4" />)}
    {replacements.length > 0 && menu(replacements, t("canvas.interactions.replace"), <Settings2 aria-hidden className="size-4" />)}
    {remaining.length > 0 && menu(remaining, t("canvas.interactions.more"), <MoreHorizontal aria-hidden className="size-4" />)}
    </>}
  </CanvasToolGroup>;
}
