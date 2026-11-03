import { MoreHorizontal, Plus, ArrowUpRight, Settings2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CanvasToolButton, CanvasToolGroup } from "@/components/canvas/CanvasTools";
import { Button } from "@/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/ui/dropdown-menu";
import { BpmnToolIcon } from "./BpmnToolIcon";
import { useRef, type ReactNode } from "react";
import type { CreationTool } from "../bpmn/elements";

/** Uses only actions offered by the existing BPMN context-pad provider. */
export function BpmnSelectionActions({ actions, count, name, onAction }: { actions: CreationTool[]; count: number; name?: string; onAction: (id: string, event: Event) => void }) {
  const { t } = useTranslation("process");
  const actionTaken = useRef(false);
  if (!count || !actions.length) return null;
  const append = actions.filter(action => action.id.startsWith("append."));
  const remaining = actions.filter(action => !action.id.startsWith("append.") && !["connect", "replace"].includes(action.id));
  const menu = (items: CreationTool[], label: string, icon: ReactNode) => <DropdownMenu><DropdownMenuTrigger asChild><Button variant="ghost" className="min-h-11 gap-2" aria-label={label}>{icon}<span className="process-selection-action-text">{label}</span></Button></DropdownMenuTrigger><DropdownMenuContent align="start" onCloseAutoFocus={event => { if (actionTaken.current) { event.preventDefault(); actionTaken.current = false; } }}>{items.map(action => <DropdownMenuItem key={action.id} onClick={event => { actionTaken.current = true; onAction(action.id, event.nativeEvent); }} className={action.id === "delete" ? "text-destructive" : undefined}><BpmnToolIcon id={action.id} />{action.title}</DropdownMenuItem>)}</DropdownMenuContent></DropdownMenu>;
  return <CanvasToolGroup label={t("canvas.interactions.selectionActions")} className="process-selection-actions">
    <span className="process-selection-label">{count > 1 ? t("canvas.interactions.selectionCount", { count }) : name || t("canvas.interactions.selected")}</span>
    {append.length > 0 && menu(append, t("canvas.interactions.append"), <Plus aria-hidden className="size-4" />)}
    {actions.some(action => action.id === "connect") && <CanvasToolButton label={t("canvas.interactions.connect")} onClick={event => onAction("connect", event.nativeEvent)}><ArrowUpRight aria-hidden /></CanvasToolButton>}
    {actions.some(action => action.id === "replace") && <CanvasToolButton label={t("canvas.interactions.replace")} onClick={event => onAction("replace", event.nativeEvent)}><Settings2 aria-hidden /></CanvasToolButton>}
    {remaining.length > 0 && menu(remaining, t("canvas.interactions.more"), <MoreHorizontal aria-hidden className="size-4" />)}
  </CanvasToolGroup>;
}
