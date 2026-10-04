import { useTranslation } from "react-i18next";
import { Button } from "@/ui/button";
import { Surface } from "@/ui/surface";
import type { CreationTool } from "../bpmn/elements";
/** The modeler's providers own the entries and actions; React supplies accessible
 * shared controls in a reserved rail outside the SVG viewport. */
export function BpmnCreationTools({ tools, isReady, onActivate }: {
  tools: CreationTool[]; isReady: boolean; onActivate: (id: string, action: "click" | "dragstart", event: Event) => void;
}) {
  const { t } = useTranslation("process");
  return <Surface asChild variant="toolbar"><nav className="process-creation-tools" aria-label={t("canvas.tools.title")}>
    {tools.map((tool) => tool.separator ? <hr key={tool.id} className="my-1 w-full border-border" /> : <Button key={tool.id} variant="ghost" size="icon-sm" disabled={!isReady} draggable onClick={(event) => onActivate(tool.id, "click", event.nativeEvent)} onDragStart={(event) => onActivate(tool.id, "dragstart", event.nativeEvent)} aria-label={t(`canvas.tools.${tool.id}`, { defaultValue: tool.title || tool.id })} title={t(`canvas.tools.${tool.id}`, { defaultValue: tool.title || tool.id })}><span aria-hidden className={`${tool.className || ""} process-creation-glyph`} /></Button>)}
  </nav></Surface>;
}
