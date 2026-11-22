import React from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/feedback";
import { Skeleton } from "@/ui/skeleton";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Button } from "@/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/ui/dropdown-menu";
import { ChevronDown, Database, Download, FileJson2, SlidersHorizontal } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogTitle } from "@/ui/dialog";
import { ROUTES } from "@/app/routes";
import { runWaitTitle } from "../runQueue";
import { SimulationBpmnView } from "../SimulationBpmnView";
import { useSimulationSection } from "../useSimulationSection";

import { SimulationConfigRail } from "../SimulationConfigRail";
import { ReadinessSummary } from "../ReadinessSummary";
import { useScenarioLab } from "../useScenarioLab";
import { ScenarioTabs } from "../ScenarioTabs";
import { exportScenarioJson, importScenarioJson } from "../scenarioJson";
import { applyNumericJsonMapping, numericJsonFields, type NumericJsonField, type NumericMapping } from "../scenarioJsonMapping";
import { changedElements } from "../scenarioWorkspace";
import { uncertainFactors } from "../sensitivity";
import { useSourceConflicts } from "../useSourceConflicts";
import { WhatIfComposer } from "../WhatIfComposer";
import type { NodeDecoration } from "../canvas/SimulationCanvas";

/**
 * Provides the scenario configuration workspace for reviewing and editing simulation assumptions.
 *
 * @returns The scenario builder page.
 */
export function ScenarioBuilderPage({ embedded = false, onDecorations }: { embedded?: boolean; onDecorations?: (items: NodeDecoration[] | null) => void } = {}): React.JSX.Element {
  const { t } = useTranslation("process");
  const navigate = useNavigate();
  const { projectId, processId, selectedElementId, selectElement, openPanel } = useSimulationSection();
  const [reference, setReference] = React.useState<"model" | "readiness" | "whatIf" | null>(null);
  const [sourceOpen, setSourceOpen] = React.useState(false);
  const [importOpen, setImportOpen] = React.useState(false);
  const [importError, setImportError] = React.useState<string | null>(null);
  const [importName, setImportName] = React.useState<string | null>(null);
  const [genericSource, setGenericSource] = React.useState<{ name: string; fields: NumericJsonField[] } | null>(null);
  const [mappingOpen, setMappingOpen] = React.useState(false);
  const [mapping, setMapping] = React.useState<NumericMapping>({ arrivalUnit: "minutes", defaultTaskUnit: "minutes", taskUnit: "minutes", tasks: {} });
  const [mappingConfirmed, setMappingConfirmed] = React.useState(false);
  const importInput = React.useRef<HTMLInputElement>(null);
  const referenceTrigger = React.useRef<HTMLElement | null>(null);
  const toolsTrigger = React.useRef<HTMLButtonElement>(null);
  const menuOpensReference = React.useRef(false);
  const pendingField = React.useRef<string | null>(null);
  const openReference = (next: "model" | "readiness" | "whatIf", opener?: HTMLElement | null) => {
    referenceTrigger.current = opener ?? document.activeElement as HTMLElement | null;
    setReference(next);
  };
  const lab = useScenarioLab();
  const {
    bpmnXml,
    template,
    templateLoading,
    claims,
    draft,
    updateDraft,
    provenance,
    confidence,
    isRunning,
    error,
    handleRun,
    handleSensitivity,
    activeRun,
  } = lab;
  const readScenarioFile = async (file: File | undefined) => {
    setImportError(null);
    setImportName(file?.name ?? null);
    setGenericSource(null);
    setMappingOpen(false);
    setMappingConfirmed(false);
    if (!file) return;
    if (file.size > 2_000_000) {
      setImportError(t("simulation.scenario.jsonTooLarge"));
      return;
    }
    try {
      const text = await file.text();
      const parsed: unknown = JSON.parse(text);
      const source = parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed as Record<string, unknown> : null;
      if (source?.format === "delir-scenario-draft") {
        const candidate = importScenarioJson(text, lab.bpmnModelId, template, draft);
        updateDraft(candidate);
        toast.success(t("simulation.scenario.importApplied"), { description: t("simulation.scenario.importAppliedDraft", { name: file.name }) });
        setImportOpen(false);
      } else if (source && "resource_profiles" in source && "task_resource_distribution" in source) {
        const candidate = importScenarioJson(text, lab.bpmnModelId, template, draft);
        updateDraft(candidate);
        toast.success(t("simulation.scenario.importApplied"), { description: t("simulation.scenario.importAppliedProsimos", {
          name: file.name, activities: Object.keys(candidate.tasks).length, resources: candidate.resources.length, decisions: Object.keys(candidate.gateways).length,
        }) });
        setImportOpen(false);
      } else {
        const fields = numericJsonFields(parsed);
        setMapping({ arrivalUnit: "minutes", defaultTaskUnit: "minutes", taskUnit: "minutes", tasks: {} });
        setGenericSource({ name: file.name, fields });
      }
    } catch (cause) {
      setImportError(cause instanceof Error ? cause.message : t("simulation.scenario.jsonInvalid"));
    }
  };
  const mappedCount = Number(Boolean(mapping.totalCases)) + Number(Boolean(mapping.arrivalIntervalMinutes)) + Number(Boolean(mapping.defaultTaskMinutes))
    + Object.values(mapping.tasks ?? {}).filter(Boolean).length
    + Object.values(mapping.resources ?? {}).flatMap((value) => Object.values(value)).filter(Boolean).length
    + Object.values(mapping.gateways ?? {}).flatMap((value) => Object.values(value)).filter(Boolean).length;
  const applyImport = () => {
    try {
      const candidate = genericSource && mappingConfirmed && mappedCount > 0 ? applyNumericJsonMapping(draft, genericSource.fields, mapping) : null;
      if (!candidate) return;
      updateDraft(candidate);
      setImportOpen(false);
      setGenericSource(null);
      if (importInput.current) importInput.current.value = "";
    } catch (cause) {
      setImportError(cause instanceof Error ? cause.message : t("simulation.scenario.jsonInvalid"));
    }
  };
  const downloadScenario = () => {
    const blob = new Blob([exportScenarioJson(draft, lab.bpmnModelId)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "delir-scenario.json";
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
  };

  // SIM-17: pannello, file del cliente e log reale messi accanto, attivita' per attivita'.
  const conflicts = useSourceConflicts(template, draft, claims);

  // SIM-25: le ipotesi incerte della bozza, da far variare nello studio di sensitivita'.
  const sensitivityFactors = React.useMemo(
    () => uncertainFactors(confidence, template, draft, t("simulation.sensitivity.arrivalLabel"), new Set(conflicts.map((c) => c.elementId))),
    [confidence, template, draft, t, conflicts],
  );

  // SIM-14: sul processo, le attivita' e le decisioni che lo scenario scelto cambia.
  const selected = lab.selectedScenario;
  const decorations = React.useMemo<NodeDecoration[] | null>(() => {
    if (!selected || selected.kind !== "alternative") return null;
    return [...changedElements(selected)].map((elementId) => ({ elementId, markers: ["sim-scenario-changed"], badge: selected.label }));
  }, [selected]);
  React.useEffect(() => { onDecorations?.(decorations); }, [decorations, onDecorations]);
  React.useEffect(() => () => onDecorations?.(null), [onDecorations]);

  const [localFocusEl, setFocusEl] = React.useState<string | null>(null);
  const focusEl = embedded ? selectedElementId ?? null : localFocusEl;
  const lowCursor = React.useRef(0);

  const reviewLowest = React.useCallback(() => {
    const ids = confidence.readiness.lowConfidenceElementIds;
    if (ids.length === 0) return;
    const next = ids[lowCursor.current % ids.length];
    lowCursor.current += 1;
    setFocusEl(next);
    selectElement?.(next);
    pendingField.current = next;
    setReference(null);
  }, [confidence.readiness.lowConfidenceElementIds, selectElement]);

  if (bpmnXml === null && !templateLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <EmptyState title={t("simulation.diagram.noModel")} />
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
        {!embedded && <header className="flex shrink-0 flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
          <h2 className="text-lg font-semibold tracking-[-0.01em] text-foreground">
            {t("simulation.scenario.pageTitle")}
          </h2>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {t("simulation.scenario.pageSubtitle")}
          </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {!embedded && <Button size="sm" variant="outline" onClick={() => openReference("model")}>{t("simulation.workspace.showModel")}</Button>}
            <Button size="sm" variant="outline" onClick={() => openReference("readiness")}>{t("simulation.workspace.assumptions")}</Button>
            {activeRun?.status === "completed" && <Button size="sm" variant="outline" onClick={() => navigate(ROUTES.projects.simulation(projectId, processId, "overview"))}>{t("simulation.workspace.viewResults")}</Button>}
          </div>
        </header>}
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        {templateLoading ? (
          <div className="grid gap-3">
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-40 w-full" />
            <Skeleton className="h-40 w-full" />
          </div>
        ) : (
          <>
          <SimulationConfigRail
            embedded
            workspace
            intro={<ScenarioTabs lab={lab} />}
            navigationActions={<div className="sim-scenario-nav-actions"><Button type="button" size="sm" variant="outline" onClick={() => setSourceOpen(true)}><SlidersHorizontal aria-hidden className="size-4" />{t("simulation.scenario.chooseSource")}</Button><DropdownMenu><DropdownMenuTrigger asChild><Button ref={toolsTrigger} size="sm" variant="outline">{t("simulation.scenario.tools")}<ChevronDown aria-hidden="true" /></Button></DropdownMenuTrigger><DropdownMenuContent align="end" onCloseAutoFocus={event => { if (menuOpensReference.current) { event.preventDefault(); menuOpensReference.current = false; } }}>
              <DropdownMenuItem onSelect={() => { menuOpensReference.current = true; openReference("whatIf", toolsTrigger.current); }}>{t("simulation.whatIf.title")}</DropdownMenuItem>
              <DropdownMenuItem onSelect={() => { menuOpensReference.current = true; openReference("readiness", toolsTrigger.current); }}>{t("simulation.workspace.assumptions")}</DropdownMenuItem>
              <DropdownMenuItem onSelect={downloadScenario}><Download aria-hidden className="size-4" />{t("simulation.scenario.exportJson")}</DropdownMenuItem>
              {activeRun?.status === "completed" && <DropdownMenuItem onSelect={() => navigate(ROUTES.projects.simulation(projectId, processId, "overview"))}>{t("simulation.workspace.viewResults")}</DropdownMenuItem>}
            </DropdownMenuContent></DropdownMenu></div>}
            template={template}
            templateLoading={templateLoading}
            claims={claims}
            draft={draft}
            onDraftChange={updateDraft}
            isRunning={isRunning}
            runningLabel={runWaitTitle(activeRun?.queue?.state, activeRun?.queue?.position, t)}
            error={error}
            onRun={() => void handleRun()}
            focusElementId={focusEl}
            provenance={confidence}
          />
          </>
        )}
      </div>

      <Dialog open={sourceOpen} onOpenChange={setSourceOpen}>
        <DialogContent className="sm:max-w-xl">
          <DialogTitle>{t("simulation.scenario.sourceTitle")}</DialogTitle>
          <DialogDescription>{t("simulation.scenario.sourceDescription")}</DialogDescription>
          <div className="sim-scenario-source-list">
            <button type="button" className="sim-scenario-source-option" onClick={() => setSourceOpen(false)}>
              <SlidersHorizontal aria-hidden className="size-5" /><span><strong>{t("simulation.scenario.sourceManual")}</strong><small>{t("simulation.scenario.sourceManualHint")}</small></span>
            </button>
            <button type="button" className="sim-scenario-source-option" onClick={() => { setSourceOpen(false); openPanel?.("eventLog"); }}>
              <Database aria-hidden className="size-5" /><span><strong>{t("simulation.scenario.sourceEventLog")}</strong><small>{t("simulation.scenario.sourceEventLogHint")}</small></span>
            </button>
            <button type="button" className="sim-scenario-source-option" onClick={() => { setSourceOpen(false); setImportOpen(true); }}>
              <FileJson2 aria-hidden className="size-5" /><span><strong>{t("simulation.scenario.sourceFile")}</strong><small>{t("simulation.scenario.sourceFileHint")}</small></span>
            </button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={importOpen} onOpenChange={(open) => { setImportOpen(open); if (!open) { setGenericSource(null); setImportError(null); if (importInput.current) importInput.current.value = ""; } }}>
        <DialogContent className="max-h-[85dvh] overflow-y-auto sm:max-w-xl">
          <DialogTitle>{t("simulation.scenario.sourceFile")}</DialogTitle>
          <DialogDescription>{t("simulation.scenario.importDescription")}</DialogDescription>
          <div className="sim-scenario-file-drop" onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); void readScenarioFile(event.dataTransfer.files[0]); }}>
            <FileJson2 aria-hidden className="size-6" />
            <p className="font-medium">{t("simulation.scenario.dropFile")}</p>
            <p className="text-sm text-muted-foreground">{t("simulation.scenario.fileTypes")}</p>
            <Button type="button" variant="outline" onClick={() => importInput.current?.click()}>{t("simulation.scenario.chooseJson")}</Button>
            <input ref={importInput} type="file" accept=".json,application/json" aria-label={t("simulation.scenario.chooseJson")} onChange={(event) => void readScenarioFile(event.target.files?.[0])} className="sr-only" />
          </div>
          {importError && <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm">
            <p className="font-medium text-destructive">{t("simulation.scenario.importNotApplied")}</p>
            <p className="mt-1 text-muted-foreground">{t("simulation.scenario.importNotAppliedHint", { name: importName })}</p>
            <details className="mt-2"><summary className="cursor-pointer text-foreground">{t("simulation.scenario.importTechnicalReason")}</summary><p className="mt-2 break-words text-muted-foreground">{importError}</p></details>
          </div>}
          {genericSource && <div className="grid gap-3 rounded-lg border border-border bg-muted/30 p-4 text-sm" role="status">
            <div>
              <p className="font-semibold">{t("simulation.scenario.fileRead")}: {genericSource.name}</p>
              <p className="mt-1 text-muted-foreground">{t("simulation.scenario.fileNeedsMapping", { count: genericSource.fields.length })}</p>
            </div>
            {genericSource.fields.length > 0 && <Button type="button" variant="outline" aria-expanded={mappingOpen} onClick={() => setMappingOpen((open) => !open)}>{t(mappingOpen ? "simulation.scenario.hideMapping" : "simulation.scenario.reviewMapping")}</Button>}
            {mappingOpen && <>
            <p className="text-muted-foreground">{t("simulation.scenario.customJsonHint")}</p>
            <div className="grid gap-3">
              <JsonFieldMapping label={t("simulation.scenario.mapCases")} fields={genericSource.fields} value={mapping.totalCases} onChange={(value) => setMapping((previous) => ({ ...previous, totalCases: value }))} />
              <JsonFieldMapping label={t("simulation.scenario.mapArrival")} fields={genericSource.fields} value={mapping.arrivalIntervalMinutes} onChange={(value) => setMapping((previous) => ({ ...previous, arrivalIntervalMinutes: value }))} />
              {mapping.arrivalIntervalMinutes && <JsonUnitSelect label={t("simulation.scenario.unit")} value={mapping.arrivalUnit ?? "minutes"} onChange={(value) => setMapping((previous) => ({ ...previous, arrivalUnit: value }))} />}
              <JsonFieldMapping label={t("simulation.scenario.mapDefaultTask")} fields={genericSource.fields} value={mapping.defaultTaskMinutes} onChange={(value) => setMapping((previous) => ({ ...previous, defaultTaskMinutes: value }))} />
              {mapping.defaultTaskMinutes && <JsonUnitSelect label={t("simulation.scenario.unit")} value={mapping.defaultTaskUnit ?? "minutes"} onChange={(value) => setMapping((previous) => ({ ...previous, defaultTaskUnit: value }))} />}
            </div>
            {template && template.tasks.length > 0 && <details className="border-t border-border pt-3">
              <summary className="cursor-pointer font-medium">{t("simulation.scenario.mapActivities")}</summary>
              <div className="mt-3 grid gap-3">
                <JsonUnitSelect label={t("simulation.scenario.activityUnit")} value={mapping.taskUnit ?? "minutes"} onChange={(value) => setMapping((previous) => ({ ...previous, taskUnit: value }))} />
                {template.tasks.map((task) => <JsonFieldMapping key={task.element_id} label={task.name} fields={genericSource.fields} value={mapping.tasks?.[task.element_id]} onChange={(value) => setMapping((previous) => ({ ...previous, tasks: { ...previous.tasks, [task.element_id]: value } }))} />)}
              </div>
            </details>}
            {draft.resources.length > 0 && <details className="border-t border-border pt-3">
              <summary className="cursor-pointer font-medium">{t("simulation.scenario.mapResources")}</summary>
              <div className="mt-3 grid gap-4">
                {draft.resources.map((resource) => <div key={resource.id} className="grid gap-2 rounded-lg border border-border p-3">
                  <p className="font-medium">{resource.name}</p>
                  <JsonFieldMapping label={t("simulation.scenario.mapAmount")} fields={genericSource.fields} value={mapping.resources?.[resource.id]?.amount} onChange={(value) => setMapping((previous) => ({ ...previous, resources: { ...previous.resources, [resource.id]: { ...previous.resources?.[resource.id], amount: value } } }))} />
                  <JsonFieldMapping label={t("simulation.scenario.mapCost")} fields={genericSource.fields} value={mapping.resources?.[resource.id]?.costPerHour} onChange={(value) => setMapping((previous) => ({ ...previous, resources: { ...previous.resources, [resource.id]: { ...previous.resources?.[resource.id], costPerHour: value } } }))} />
                </div>)}
              </div>
            </details>}
            {template && template.gateways.length > 0 && <details className="border-t border-border pt-3">
              <summary className="cursor-pointer font-medium">{t("simulation.scenario.mapDecisions")}</summary>
              <div className="mt-3 grid gap-4">
                <label className="grid gap-1.5"><span className="font-medium">{t("simulation.scenario.probabilityUnit")}</span><select className="min-h-10 w-full rounded-lg border border-border bg-background px-3" value={mapping.probabilityUnit ?? "percent"} onChange={(event) => setMapping((previous) => ({ ...previous, probabilityUnit: event.target.value as "fraction" | "percent" }))}><option value="percent">0–100%</option><option value="fraction">0–1</option></select></label>
                {template.gateways.flatMap((gateway) => gateway.branches.map((branch) => <JsonFieldMapping key={`${gateway.element_id}:${branch.flow_id}`} label={`${gateway.name}: ${branch.flow_name || branch.target_name || branch.flow_id}`} fields={genericSource.fields} value={mapping.gateways?.[gateway.element_id]?.[branch.flow_id]} onChange={(value) => setMapping((previous) => ({ ...previous, gateways: { ...previous.gateways, [gateway.element_id]: { ...previous.gateways?.[gateway.element_id], [branch.flow_id]: value } } }))} />))}
              </div>
            </details>}
            <p className="text-muted-foreground">{t("simulation.scenario.mappingStatus", { mapped: mappedCount, available: genericSource.fields.length })}</p>
            <label className="flex items-start gap-2"><input type="checkbox" className="mt-0.5" checked={mappingConfirmed} onChange={(event) => setMappingConfirmed(event.target.checked)} /><span>{t("simulation.scenario.mappingConfirm")}</span></label>
            </>}
          </div>}
          <DialogFooter>
            {genericSource && <Button type="button" variant="outline" onClick={() => setImportOpen(false)}>{t("simulation.scenario.configureInEditor")}</Button>}
            <Button type="button" variant="ghost" onClick={() => setImportOpen(false)}>{t("simulation.scenarios.cancel")}</Button>
            {genericSource && mappingOpen && <Button type="button" disabled={!mappingConfirmed || mappedCount === 0} onClick={applyImport}>{t("simulation.scenario.applyMappedJson")}</Button>}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={reference !== null} onOpenChange={(open) => { if (!open) setReference(null); }}>
        <DialogContent aria-describedby={undefined} onCloseAutoFocus={(event) => {
          event.preventDefault();
          const field = pendingField.current ? document.querySelector<HTMLElement>(`[data-sim-el="${CSS.escape(pendingField.current)}"] input, [data-sim-el="${CSS.escape(pendingField.current)}"] button`) : null;
          (field ?? referenceTrigger.current)?.focus({ preventScroll: true });
          pendingField.current = null;
        }} className={reference === "model" ? "flex h-[85dvh] flex-col border-border sm:max-w-[calc(100vw-4rem)]" : "max-h-[85dvh] overflow-y-auto border-border sm:max-w-lg"}>
          <DialogTitle>{t(reference === "model" ? "simulation.diagram.title" : reference === "whatIf" ? "simulation.whatIf.title" : "simulation.workspace.assumptions")}</DialogTitle>
          {reference === "model" ? <SimulationBpmnView className="min-h-0 flex-1" bpmnXml={bpmnXml} selectedElementId={focusEl} onSelectElement={(id) => { if (id && (draft.tasks[id] || draft.gateways[id])) { setFocusEl(id); pendingField.current = id; setReference(null); } }} /> : reference === "whatIf" ? <WhatIfComposer embedded bpmnModelId={lab.bpmnModelId} template={template} draft={draft} onApply={updateDraft} /> :
          <ReadinessSummary
            confidence={confidence}
            provenance={provenance}
            onReview={
              confidence.readiness.lowConfidenceElementIds.length > 0
                ? reviewLowest
                : undefined
            }
            conflicts={conflicts}
            sensitivity={{
              factors: sensitivityFactors,
              disabled: isRunning,
              onStart: () => { setReference(null); void handleSensitivity(sensitivityFactors); },
            }}
          />
          }
        </DialogContent>
      </Dialog>
    </div>
  );
}

function JsonFieldMapping({ label, fields, value, onChange }: { label: string; fields: NumericJsonField[]; value?: string; onChange: (value: string | undefined) => void }) {
  const { t } = useTranslation("process");
  return <label className="grid gap-1.5"><span className="font-medium">{label}</span><select className="min-h-10 w-full rounded-lg border border-border bg-background px-3" value={value ?? ""} onChange={(event) => onChange(event.target.value || undefined)}>
    <option value="">{t("simulation.scenario.doNotMap")}</option>
    {fields.map((field) => <option key={field.path} value={field.path}>{field.path} · {field.value}</option>)}
  </select></label>;
}

function JsonUnitSelect({ label, value, onChange }: { label: string; value: "seconds" | "minutes" | "hours"; onChange: (value: "seconds" | "minutes" | "hours") => void }) {
  const { t } = useTranslation("process");
  return <label className="grid gap-1.5"><span className="font-medium">{label}</span><select className="min-h-10 w-full rounded-lg border border-border bg-background px-3" value={value} onChange={(event) => onChange(event.target.value as "seconds" | "minutes" | "hours")}>
    <option value="seconds">{t("simulation.scenario.seconds")}</option>
    <option value="minutes">{t("simulation.scenario.minutes")}</option>
    <option value="hours">{t("simulation.scenario.hours")}</option>
  </select></label>;
}
