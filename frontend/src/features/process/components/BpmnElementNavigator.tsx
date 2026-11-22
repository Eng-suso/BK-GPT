import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Circle, Diamond, Square, X, Cog } from "lucide-react";
import { Button } from "@/ui/button";
import { Input } from "@/ui/input";
import { Surface } from "@/ui/surface";
import type { CanvasElement } from "../bpmn/elements";
import { elementHierarchy } from "../bpmn/elementHierarchy";
import { bpmnTypeTool } from "../bpmn/presentation";
export function BpmnElementNavigator({ elements, selectedId, isReady, onSelect, onClose }: {
  elements: CanvasElement[]; selectedId?: string; isReady: boolean; onSelect: (id: string) => void; onClose: () => void;
}) {
  const { t } = useTranslation("process");
  const [query, setQuery] = useState("");
  const rows = elementHierarchy(elements, query);
  return <Surface asChild variant="rail"><aside className="process-element-navigator" aria-label={t("canvas.elements.title")}>
    <div className="flex items-center justify-between gap-2 px-3 py-3">
      <h3 className="text-sm font-semibold">{t("canvas.elements.title")} <span className="ml-1 text-xs font-normal tabular-nums text-muted-foreground">{elements.length}</span></h3>
      <Button variant="ghost" size="icon-sm" aria-label={t("canvas.elements.close")} onClick={onClose}><X aria-hidden /></Button>
    </div>
    <div className="px-3 pb-3"><Input aria-label={t("canvas.elements.search")} placeholder={t("canvas.elements.search")} value={query} onChange={(event) => setQuery(event.target.value)} /></div>
    <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
      {!isReady ? <p className="p-2 text-sm text-muted-foreground">{t("canvas.elements.loading")}</p> : rows.length ? <ul className="space-y-1">{rows.map(({ element: el, depth }) => {
        const Icon = el.kind === "gateway" ? Diamond : el.kind === "start" || el.kind === "end" ? Circle : el.kind === "automation" ? Cog : Square;
        const typeName = bpmnTypeTool[el.type] ? t(`canvas.tools.${bpmnTypeTool[el.type]}`) : el.type;
        return <li key={el.id}><Button variant={selectedId === el.id ? "secondary" : "ghost"} className="h-auto min-h-11 w-full justify-start whitespace-normal rounded-lg px-2 py-2 text-left" style={{ paddingInlineStart: 8 + depth * 16 }} aria-pressed={selectedId === el.id} onClick={() => onSelect(el.id)}>
          <Icon aria-hidden className={`size-4 shrink-0 process-element-icon--${el.kind}`} />
          <span className="min-w-0"><span className="block break-words text-xs">{el.name || t("canvas.elements.unnamed", { type: typeName })}</span><span className="block text-micro font-normal text-muted-foreground">{typeName}</span></span>
        </Button></li>;
      })}</ul> : <p className="p-2 text-sm text-muted-foreground">{t(query ? "canvas.elements.noMatches" : "canvas.elements.empty")}</p>}
    </div>
  </aside></Surface>;
}
