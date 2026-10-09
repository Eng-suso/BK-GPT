import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Library, Search, X } from "lucide-react";
import { Button } from "@/ui/button";
import { Input } from "@/ui/input";
import { Surface } from "@/ui/surface";
import type { CreationTool } from "../bpmn/elements";

const GROUPS = ["event", "activity", "gateway", "data", "collaboration", "artifact"];
const QUICK = ["create.start-event", "create.task", "create.end-event", "create.exclusive-gateway", "create.participant-expanded", "create.lane"];
/** Providers retain BPMN rules, placement, connections and undo. */
export function BpmnCreationTools({ tools, isReady, onActivate }: {
  tools: CreationTool[]; isReady: boolean; onActivate: (id: string, action: "click" | "dragstart", event: Event) => void;
}) {
  const { t } = useTranslation("process");
  const [expanded, setExpanded] = useState(false);
  const [search, setSearch] = useState("");
  const [recent, setRecent] = useState<string[]>([]);
  const trigger = useRef<HTMLButtonElement>(null);
  const close = () => { setExpanded(false); requestAnimationFrame(() => trigger.current?.focus()); };
  const title = (tool: CreationTool) => t(`canvas.tools.${tool.id}`, { defaultValue: tool.title || tool.id });
  const activate = (tool: CreationTool, action: "click" | "dragstart", event: Event) => {
    if (!isReady) return;
    setRecent(previous => [tool.id, ...previous.filter(id => id !== tool.id)].slice(0, 6));
    onActivate(tool.id, action, event);
  };
  const renderTool = (tool: CreationTool, compact = false) => <Button key={tool.id} variant="ghost" size={compact ? "icon-sm" : "sm"} disabled={!isReady} draggable onClick={event => activate(tool, "click", event.nativeEvent)} onDragStart={event => activate(tool, "dragstart", event.nativeEvent)} aria-label={title(tool)} title={title(tool)} className={compact ? undefined : "process-library-entry"}><span aria-hidden className={`${tool.className || "bpmn-icon-task"} process-creation-glyph`} />{!compact && <span>{title(tool)}</span>}</Button>;
  const query = search.trim().toLocaleLowerCase();
  const shapes = tools.filter(tool => !tool.separator && tool.group !== "tools");
  const matches = shapes.filter(tool => `${title(tool)} ${tool.id}`.toLocaleLowerCase().includes(query));
  const group = (tool: CreationTool) => tool.group?.startsWith("data-") ? "data" : tool.group;
  return <Surface asChild variant="toolbar"><nav className={`process-creation-tools ${expanded ? "process-creation-tools--expanded" : ""}`} aria-label={t("canvas.tools.title")} onKeyDown={event => { if (event.key === "Escape" && expanded) { event.preventDefault(); event.stopPropagation(); close(); } }}>
    <div className="process-library-toggle"><Button ref={trigger} variant="ghost" size={expanded ? "sm" : "icon-sm"} aria-label={t("canvas.library.toggle")} aria-expanded={expanded} onClick={() => expanded ? close() : setExpanded(true)}><Library aria-hidden />{expanded && t("canvas.library.title")}</Button>{expanded && <Button variant="ghost" size="icon-sm" aria-label={t("canvas.library.close")} onClick={close}><X aria-hidden /></Button>}</div>
    {expanded ? <>
      <label className="process-library-search"><Search aria-hidden className="size-4" /><Input value={search} onChange={event => setSearch(event.target.value)} aria-label={t("canvas.library.search")} placeholder={t("canvas.library.search")} /></label>
      <p className="px-3 text-xs text-muted-foreground">{t("canvas.library.hint")}</p>
      {!query && <><section className="process-library-section"><h3>{t("canvas.library.recent")}</h3>{recent.length ? recent.map(id => shapes.find(tool => tool.id === id)).filter((tool): tool is CreationTool => Boolean(tool)).map(tool => renderTool(tool)) : <p className="text-xs text-muted-foreground">{t("canvas.library.noRecent")}</p>}</section><section className="process-library-section"><h3>{t("canvas.library.quick")}</h3><div className="process-library-quick">{QUICK.map(id => shapes.find(tool => tool.id === id)).filter((tool): tool is CreationTool => Boolean(tool)).map(tool => renderTool(tool))}</div></section></>}
      {query ? <section className="process-library-section" aria-live="polite">{matches.length ? matches.map(tool => renderTool(tool)) : <p className="text-sm text-muted-foreground">{t("canvas.library.noResults")}</p>}</section> : GROUPS.map(key => <details key={key} className="process-library-category" open={key === "event" || key === "activity"}><summary>{t(`canvas.library.groups.${key}`)}<span>{shapes.filter(tool => group(tool) === key).length}</span></summary>{shapes.filter(tool => group(tool) === key).map(tool => renderTool(tool))}</details>)}
      <section className="process-library-section"><h3>{t("canvas.library.navigation")}</h3><div className="flex gap-1">{tools.filter(tool => !tool.separator && tool.group === "tools").map(tool => renderTool(tool, true))}</div></section>
    </> : tools.filter(tool => !tool.id.startsWith("create.") || QUICK.includes(tool.id) || ["create.intermediate-event", "create.data-object", "create.data-store", "create.subprocess-expanded", "create.group"].includes(tool.id)).map(tool => tool.separator ? <hr key={tool.id} className="my-1 w-full border-border" /> : renderTool(tool, true))}
  </nav></Surface>;
}
