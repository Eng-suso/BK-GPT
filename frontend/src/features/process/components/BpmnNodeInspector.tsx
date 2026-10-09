import { useTranslation } from "react-i18next";
import { Trash2, X, MessagesSquare } from "lucide-react";
import { Badge } from "@/ui/badge";
import { Button } from "@/ui/button";
import { Input } from "@/ui/input";
import { Textarea } from "@/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/ui/tabs";
import type { BpmnVersion } from "@/contracts/workspace";
import type { SelectedBpmnElement } from "../bpmn/types";
import type { EnterpriseMetadata, EnterpriseField } from "../bpmn/enterprise";

type Props = {
  element: SelectedBpmnElement; onNameChange: (name: string) => void; onDocChange: (doc: string) => void;
  onMetadataChange: (patch: Partial<EnterpriseMetadata>) => void; onDelete: () => void;
  onClose: () => void; onAsk?: () => void; versions: BpmnVersion[]; embedded?: boolean;
};
const TABS = ["details", "rules", "data", "files", "history", "ai"] as const;
export function BpmnNodeInspector({ element, onNameChange, onDocChange, onMetadataChange, onDelete, onClose, onAsk, versions, embedded = false }: Props) {
  const { t, i18n } = useTranslation("process");
  const field = (name: Exclude<EnterpriseField, "required">, multiline = false) => <label className="grid gap-1.5" key={name}><span className="text-xs font-medium text-muted-foreground">{t(`properties.enterprise.fields.${name}`)}</span>{multiline ? <Textarea rows={3} value={element.metadata[name]} onChange={event => onMetadataChange({ [name]: event.target.value })} /> : <Input value={element.metadata[name]} onChange={event => onMetadataChange({ [name]: event.target.value })} />}</label>;
  return <aside className="process-bpmn-node-inspector process-enterprise-properties ui-surface ui-surface-panel" aria-label={t("canvas.inspectorLabel")}>
    <header className="flex items-start justify-between gap-2 border-b border-border p-4"><div className="min-w-0"><Badge variant="outline" className="text-[10px] uppercase">{element.type}</Badge><strong className="mt-1 block break-words text-sm">{element.name || element.id}</strong><span className="text-xs text-muted-foreground break-all">{element.id}</span></div>{!embedded && <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label={t("canvas.inspectorClose")}><X aria-hidden /></Button>}</header>
    <Tabs key={element.id} defaultValue="details" className="min-h-0 flex-1 gap-0">
      <div className="overflow-x-auto shrink-0 border-b border-border p-2"><TabsList aria-label={t("properties.enterprise.tabsLabel")} className="min-w-full">{TABS.map(tab => <TabsTrigger key={tab} value={tab} className="px-2 text-xs">{t(`properties.enterprise.tabs.${tab}`)}</TabsTrigger>)}</TabsList></div>
      <div className="min-h-0 flex-1 overflow-y-auto ui-scrollbar p-4">
        <TabsContent value="details" className="grid gap-4"><label className="grid gap-1.5"><span className="text-xs font-medium text-muted-foreground">{t("properties.enterprise.name")}</span><Input value={element.name} onChange={event => onNameChange(event.target.value)} /></label>{field("owner")}{field("office")}<label className="grid gap-1.5"><span className="text-xs font-medium text-muted-foreground">{t("properties.enterprise.description")}</span><Textarea rows={4} value={element.documentation} onChange={event => onDocChange(event.target.value)} /></label><label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={element.metadata.required} onChange={event => onMetadataChange({ required: event.target.checked })} />{t("properties.enterprise.required")}</label><p className="text-xs text-muted-foreground">{t("properties.enterprise.saveHint")}</p></TabsContent>
        <TabsContent value="rules" className="grid gap-4">{field("rules", true)}{field("risks", true)}{field("sop", true)}</TabsContent>
        <TabsContent value="data" className="grid gap-4">{field("inputs", true)}{field("outputs", true)}{field("systems", true)}</TabsContent>
        <TabsContent value="files" className="grid gap-4"><p className="text-xs text-muted-foreground">{t("properties.enterprise.filesHint")}</p>{field("files", true)}</TabsContent>
        <TabsContent value="history" className="grid gap-3"><p className="text-xs text-muted-foreground">{t("properties.enterprise.historyHint")}</p>{versions.length ? <ol className="grid gap-3">{versions.map(version => <li key={version.id} className="border-b border-border pb-2 text-xs"><strong>V{version.id} · {version.changeSummary || version.source}</strong><time className="mt-1 block text-muted-foreground" dateTime={version.createdAt}>{new Date(version.createdAt).toLocaleString(i18n.language)}</time></li>)}</ol> : <p className="text-sm text-muted-foreground">{t("properties.enterprise.noHistory")}</p>}</TabsContent>
        <TabsContent value="ai" className="grid gap-4"><p className="text-sm text-muted-foreground">{t("properties.enterprise.aiHint")}</p>{onAsk && <Button size="sm" variant="outline" onClick={onAsk}><MessagesSquare aria-hidden />{t("properties.enterprise.ask")}</Button>}</TabsContent>
      </div>
    </Tabs>
    <footer className="shrink-0 border-t border-border p-3"><Button variant="outline" size="sm" className="w-full text-destructive" onClick={onDelete}><Trash2 aria-hidden />{t("properties.enterprise.delete")}</Button></footer>
  </aside>;
}
