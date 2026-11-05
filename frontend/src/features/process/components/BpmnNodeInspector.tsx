import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Trash2, X, MessagesSquare } from "lucide-react";
import { Button } from "@/ui/button";
import { Input } from "@/ui/input";
import { Textarea } from "@/ui/textarea";
import { Surface } from "@/ui/surface";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/ui/select";
import { EditorWorkspace, EditorBody, EditorActions } from "@/components/form/EditorWorkspace";
import { BpmnToolIcon } from "./BpmnToolIcon";
import { bpmnTypeTool } from "../bpmn/presentation";
import type { BpmnVersion } from "@/contracts/workspace";
import type { SelectedBpmnElement } from "../bpmn/types";
import type { EnterpriseMetadata, EnterpriseField } from "../bpmn/enterprise";

type Props = {
  element: SelectedBpmnElement; onNameChange: (name: string) => void; onDocChange: (doc: string) => void;
  onMetadataChange: (patch: Partial<EnterpriseMetadata>) => void; onDelete: () => void;
  onClose: () => void; onAsk?: () => void; versions: BpmnVersion[]; embedded?: boolean;
};
const SECTIONS = ["details", "rules", "data", "files", "history", "ai"] as const;

export function BpmnNodeInspector({ element, onNameChange, onDocChange, onMetadataChange, onDelete, onClose, onAsk, versions, embedded = false }: Props) {
  const { t, i18n } = useTranslation("process");
  const [section, setSection] = useState<string>("details");
  const isContainer = element.type === "Participant" || element.type === "Lane";
  const isConnection = /Flow$|Association$/.test(element.type);
  const typeTool = bpmnTypeTool[element.type];
  const typeName = typeTool === "create.task" ? t("canvas.legend.task") : typeTool ? t("canvas.tools." + typeTool) : element.type;
  const field = (name: Exclude<EnterpriseField, "required">, multiline = false) =>
    <label className="ui-editor-field" key={name}>
      <span>{t("properties.enterprise.fields." + name)}</span>
      {multiline ? <Textarea rows={3} value={element.metadata[name]} onChange={event => onMetadataChange({ [name]: event.target.value })} />
        : <Input value={element.metadata[name]} onChange={event => onMetadataChange({ [name]: event.target.value })} />}
    </label>;
  return <Surface asChild variant="panel"><aside className="process-bpmn-node-inspector process-enterprise-properties" aria-label={t("canvas.inspectorLabel")}>
    <header className="process-properties-identity">
      <span className="process-properties-symbol"><BpmnToolIcon id={typeTool ?? "create.task"} /></span>
      <div className="min-w-0 flex-1"><p className="text-xs text-muted-foreground">{typeName}</p><h3 className="mt-1 break-words text-base font-semibold">{element.name || typeName}</h3></div>
      {!embedded && <Button variant="ghost" size="icon" onClick={onClose} aria-label={t("canvas.inspectorClose")}><X aria-hidden /></Button>}
    </header>
    <EditorWorkspace className="flex-1">
      <div className="ui-editor-navigation">
        <Select value={section} onValueChange={setSection}>
          <SelectTrigger className="min-w-0 flex-1" aria-label={t("canvas.interactions.section")}><SelectValue /></SelectTrigger>
          <SelectContent>{SECTIONS.map(value => <SelectItem key={value} value={value}>{t("properties.enterprise.tabs." + value)}</SelectItem>)}</SelectContent>
        </Select>
      </div>
      <EditorBody>
        <div className="grid gap-5">
          {section === "details" && <>
            <label className="ui-editor-field"><span>{t("properties.enterprise.name")}</span><Input value={element.name} onChange={event => onNameChange(event.target.value)} /></label>
            {!isContainer && !isConnection && <>{field("owner")}{field("office")}</>}
            <label className="ui-editor-field"><span>{t("properties.enterprise.description")}</span><Textarea rows={4} value={element.documentation} onChange={event => onDocChange(event.target.value)} /></label>
            {!isContainer && !isConnection && <label className="flex min-h-11 items-center gap-3 text-sm"><input type="checkbox" className="size-4 shrink-0 accent-primary" checked={element.metadata.required} onChange={event => onMetadataChange({ required: event.target.checked })} />{t("properties.enterprise.required")}</label>}
            {!isContainer && !isConnection && <p className="text-xs leading-relaxed text-muted-foreground">{t("properties.enterprise.saveHint")}</p>}
            <details className="process-properties-technical"><summary>{t("canvas.interactions.identity")}</summary><dl><dt>ID</dt><dd>{element.id}</dd><dt>BPMN</dt><dd>{element.type}</dd></dl></details>
          </>}
          {section === "rules" && <>{field("rules", true)}{field("risks", true)}{field("sop", true)}</>}
          {section === "data" && <>{field("inputs", true)}{field("outputs", true)}{field("systems", true)}</>}
          {section === "files" && <><p className="text-sm leading-relaxed text-muted-foreground">{t("properties.enterprise.filesHint")}</p>{field("files", true)}</>}
          {section === "history" && <><p className="text-sm leading-relaxed text-muted-foreground">{t("properties.enterprise.historyHint")}</p>{versions.length ? <ol className="grid gap-4">{versions.map(version => <li key={version.id} className="border-b border-border pb-3 text-sm"><strong>V{version.id} · {version.changeSummary || version.source}</strong><time className="mt-1 block text-xs text-muted-foreground" dateTime={version.createdAt}>{new Date(version.createdAt).toLocaleString(i18n.language)}</time></li>)}</ol> : <p className="text-sm text-muted-foreground">{t("properties.enterprise.noHistory")}</p>}</>}
          {section === "ai" && <><p className="text-sm leading-relaxed text-muted-foreground">{t("properties.enterprise.aiHint")}</p>{onAsk && <Button variant="outline" onClick={onAsk}><MessagesSquare aria-hidden />{t("properties.enterprise.ask")}</Button>}</>}
        </div>
      </EditorBody>
      {!isContainer && <EditorActions><Button variant="ghost" className="min-h-11 text-destructive" onClick={onDelete}><Trash2 aria-hidden />{t("properties.enterprise.delete")}</Button></EditorActions>}
    </EditorWorkspace>
  </aside></Surface>;
}
