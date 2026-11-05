import { useTranslation } from "react-i18next";
import { Button } from "@/ui/button";
import { bpmnTypeTool } from "../bpmn/presentation";
import { BpmnToolIcon } from "./BpmnToolIcon";
import type { SelectionItem } from "../bpmn/useBpmnCanvasUi";

/** Progressive disclosure of the selection; choosing a row uses native selection. */
export function BpmnSelectionSummary({ items, onSelect }: { items: SelectionItem[]; onSelect: (id: string) => unknown }) {
  const { t } = useTranslation("process");
  return <div className="process-selection-summary">
    <p className="text-sm text-muted-foreground">{t("canvas.interactions.multipleHint")}</p>
    <ul>{items.map(item => { const tool = bpmnTypeTool[item.type]; const typeName = tool ? t("canvas.tools." + tool) : t(/Flow$|Association$/.test(item.type) ? "canvas.interactions.connection" : "canvas.interactions.selected"); return <li key={item.id}><Button variant="ghost" className="h-auto min-h-11 w-full justify-start whitespace-normal px-3 py-2 text-left" onClick={() => onSelect(item.id)}>
      <BpmnToolIcon id={tool ?? "connect"} /><span className="min-w-0"><span className="block break-words text-sm">{item.name || typeName}</span><span className="block text-xs font-normal text-muted-foreground">{item.name ? typeName : ""}</span></span>
    </Button></li>; })}</ul>
  </div>;
}
