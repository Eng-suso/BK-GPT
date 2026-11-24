import React from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Trash2, Upload, X } from "lucide-react";

import { ConfirmDialog, EmptyState, InlineNotice } from "@/components/feedback";
import { StatTile } from "@/components/data";
import { httpErrorMessage } from "@/lib/http";
import { Button } from "@/ui/button";
import { Skeleton } from "@/ui/skeleton";

import type { NodeDecoration } from "../canvas/SimulationCanvas";
import { fetchScenarioTemplate } from "../simulationApi";
import { formatDuration } from "../simulationResults";
import { useSimulationSection } from "../useSimulationSection";
import {
  addAttribute,
  draftFromMapping,
  draftIssues,
  matchesFrom,
  missingTemplateColumns,
  toColumnMapping,
  usedColumns,
  type MappingDraft,
  type Thousands,
} from "./eventLogMapping";
import {
  ATTRIBUTE_TYPES,
  DELIMITERS,
  type AttributeColumn,
  type AttributeType,
  type Delimiter,
  type EventLog,
  type EventLogAnalysis,
  type EventLogTemplate,
} from "./eventLogTypes";
import {
  useApplyEventLogMapping,
  useDeleteEventLog,
  useEventLogAnalysis,
  useEventLogPreview,
  useEventLogs,
  useEventLogTemplates,
  useSaveEventLogTemplate,
  useUploadEventLog,
} from "./useEventLogImport";
import { ConformanceStep } from "./ConformanceStep";
import { RealVsSimulatedStep } from "./RealVsSimulatedStep";
import { DATE_FORMATS, detectDateFormat, detectNumberFormat, suggestColumns } from "./eventLogSuggestions";
import "./eventLog.css";

const STEPS = ["columns", "formats", "results", "activities", "resources", "conformance", "compare"] as const;
type Step = (typeof STEPS)[number];
const PREVIEW_ROWS = 20;
const ACCEPT = ".csv,.tsv,.txt,.xes";

/**
 * Import di un event log reale sul processo: file, mapping, qualita', KPI,
 * abbinamenti al modello e confronto con un run simulato. `onDecorations`
 * porta gli scarti del confronto sul disegno (null = nessun overlay).
 */
export function EventLogPanel({ onDecorations }: { onDecorations?: (items: NodeDecoration[] | null) => void } = {}): React.JSX.Element {
  const { t } = useTranslation("process");
  const { processId } = useSimulationSection();
  const logs = useEventLogs(processId);
  const upload = useUploadEventLog(processId);
  const remove = useDeleteEventLog(processId);
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  // Il log da eliminare: si chiede prima, il file e l'analisi non si recuperano.
  const [deleting, setDeleting] = React.useState<EventLog | null>(null);
  const fileRef = React.useRef<HTMLInputElement>(null);
  const selected = logs.data?.find((log) => log.id === selectedId) ?? null;

  const onFile = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    upload.mutate(
      { file },
      { onSuccess: (log) => setSelectedId(log.id) },
    );
  };

  if (selected) {
    return <EventLogWizard key={selected.id} log={selected} onClose={() => setSelectedId(null)} onDecorations={onDecorations} />;
  }

  return (
    <div className="sim-eventlog">
      <p className="sim-eventlog-hint">{t("simulation.eventLog.intro")}</p>
      <div className="sim-eventlog-upload">
        <span className="sim-eventlog-hint">{t("simulation.eventLog.autoRead")}</span>
        <input ref={fileRef} type="file" accept={ACCEPT} className="sr-only" aria-label={t("simulation.eventLog.file")} onChange={onFile} />
        <Button size="sm" onClick={() => fileRef.current?.click()} disabled={upload.isPending}>
          <Upload aria-hidden className="size-4" />
          {upload.isPending ? t("simulation.eventLog.uploading") : t("simulation.eventLog.upload")}
        </Button>
      </div>
      {upload.isError && (
        <InlineNotice tone="error" title={t("simulation.eventLog.uploadFailed")}>
          {httpErrorMessage(upload.error, t("simulation.eventLog.uploadFailed"))}
        </InlineNotice>
      )}
      {logs.isError && (
        <InlineNotice
          tone="error"
          title={t("simulation.eventLog.loadFailed")}
          action={<Button size="sm" variant="outline" onClick={() => void logs.refetch()}>{t("simulation.eventLog.retry")}</Button>}
        />
      )}
      {logs.isPending && (
        <div className="sim-eventlog-list" aria-hidden>
          <Skeleton className="h-11 w-full" />
          <Skeleton className="h-11 w-full" />
        </div>
      )}
      {logs.data?.length === 0 && <EmptyState title={t("simulation.eventLog.empty")} description={t("simulation.eventLog.emptyHint")} />}
      {logs.data && logs.data.length > 0 && (
        <ul className="sim-eventlog-list" aria-label={t("simulation.eventLog.list")}>
          {logs.data.map((log) => (
            <li key={log.id}>
              <button type="button" className="sim-eventlog-item" onClick={() => setSelectedId(log.id)}>
                <strong>{log.name}</strong>
                <span>
                  {t("simulation.eventLog.rows", { count: log.row_count })} · {t(`simulation.eventLog.status.${log.status}`)}
                  {log.template ? ` · ${log.template.name} v${log.template.version}` : ""}
                </span>
              </button>
              <Button size="icon" variant="ghost" aria-label={t("simulation.eventLog.delete", { name: log.name })} disabled={remove.isPending} onClick={() => setDeleting(log)}>
                <Trash2 aria-hidden className="size-4" />
              </Button>
            </li>
          ))}
        </ul>
      )}
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
        title={t("simulation.eventLog.deleteTitle", { name: deleting?.name ?? "" })}
        description={t("simulation.eventLog.deleteDescription")}
        confirmLabel={t("simulation.eventLog.deleteConfirm")}
        destructive
        onConfirm={async () => {
          if (deleting) await remove.mutateAsync(deleting.id);
        }}
      />
    </div>
  );
}

function delimiterKey(value: string): string {
  return { ",": "comma", ";": "semicolon", "\t": "tab", "|": "pipe" }[value] ?? "comma";
}

function EventLogWizard({ log, onClose, onDecorations }: {
  log: EventLog;
  onClose: () => void;
  onDecorations?: (items: NodeDecoration[] | null) => void;
}): React.JSX.Element {
  const { t } = useTranslation("process");
  const { processId, process } = useSimulationSection();
  const [step, setStep] = React.useState<Step>(log.status === "mapped" ? "results" : "columns");
  const [delimiter, setDelimiter] = React.useState<Delimiter | null>(null);
  const [draftInput, setDraft] = React.useState<MappingDraft>(() => (log.mapping ? draftFromMapping(log.mapping) : suggestColumns(log.columns)));
  const [showAllRows, setShowAllRows] = React.useState(false);
  const [page, setPage] = React.useState(0);
  const [dateConfirmed, setDateConfirmed] = React.useState(Boolean(log.mapping));
  const [manualDateFormat, setManualDateFormat] = React.useState(Boolean(log.mapping));
  const [manualNumberFormat, setManualNumberFormat] = React.useState(Boolean(log.mapping));
  const [templateId, setTemplateId] = React.useState<number | null>(log.template?.id ?? null);
  const pageSize = showAllRows ? 50 : PREVIEW_ROWS;
  const sample = useEventLogPreview(log.id, delimiter);
  const preview = useEventLogPreview(log.id, delimiter, page * pageSize, pageSize);
  const stored = useEventLogAnalysis(log.id, log.status === "mapped");
  const apply = useApplyEventLogMapping(processId, log.id);
  const templates = useEventLogTemplates();
  const model = useQuery({
    queryKey: ["workspace", "simulation-template", process.bpmnModelId],
    queryFn: () => fetchScenarioTemplate(process.bpmnModelId, null),
    staleTime: 60_000,
    retry: false,
  });
  const analysis: EventLogAnalysis | null = apply.data ?? stored.data ?? null;
  const columns = sample.data?.columns ?? log.columns;
  const dateColumn = draftInput.timeShape === "interval" ? draftInput.end : draftInput.timestamp;
  const dateValues = sample.data?.sample_rows.map((row) => row[columns.indexOf(dateColumn)] ?? "") ?? [];
  const detectedDate = detectDateFormat(dateValues);
  const costColumn = draftInput.cost || draftInput.caseAttributes.find((item) => item.type === "number")?.column || draftInput.eventAttributes.find((item) => item.type === "number")?.column;
  const numberFormat = sample.data && costColumn
    ? detectNumberFormat(sample.data.sample_rows.map((row) => row[columns.indexOf(costColumn)] ?? ""))
    : null;
  const draft: MappingDraft = {
    ...draftInput,
    ...(!manualDateFormat && dateColumn && sample.data && !detectedDate.ambiguous ? { pattern: detectedDate.pattern } : {}),
    ...(!manualNumberFormat && numberFormat ? numberFormat : {}),
  };
  const issues = draftIssues(draft);
  const needsDateChoice = Boolean(dateColumn && dateValues.some(Boolean) && detectedDate.ambiguous && !dateConfirmed);
  const update = (patch: Partial<MappingDraft>) => {
    if (patch.timestamp !== undefined || patch.end !== undefined || patch.timeShape !== undefined) {
      setManualDateFormat(false);
      setDateConfirmed(false);
    }
    if (patch.cost !== undefined || patch.caseAttributes !== undefined || patch.eventAttributes !== undefined) setManualNumberFormat(false);
    if (patch.pattern !== undefined) setManualDateFormat(true);
    if (patch.decimal !== undefined || patch.thousands !== undefined) setManualNumberFormat(true);
    setDraft((current) => ({ ...current, ...patch }));
    setTemplateId(null);
  };

  const run = (matches?: { activityMatches?: Record<string, string | null>; resourceMatches?: Record<string, string | null> }) =>
    apply.mutate(
      {
        // Il template applicato e non modificato resta il riferimento del log.
        ...(templateId !== null ? { templateId } : { mapping: toColumnMapping(draft) }),
        delimiter: delimiter ?? undefined,
        activityMatches: matches?.activityMatches ?? (analysis?.activities.confirmed ? matchesFrom(analysis.activities.matches, (m) => m.activity) : undefined),
        resourceMatches: matches?.resourceMatches ?? (analysis?.resources.confirmed ? matchesFrom(analysis.resources.matches, (m) => m.resource) : undefined),
      },
      { onSuccess: () => setStep((current) => (current === "formats" || current === "columns" ? "results" : current)) },
    );
  const applyTemplate = (template: EventLogTemplate) => {
    setManualDateFormat(true);
    setManualNumberFormat(true);
    setDraft(draftFromMapping(template.mapping));
    setTemplateId(template.id);
    apply.mutate({ templateId: template.id, delimiter: delimiter ?? undefined }, { onSuccess: () => setStep("results") });
  };

  return (
    <div className="sim-eventlog">
      <div className="sim-eventlog-head">
        <strong>{log.name}</strong>
        <Button size="icon" variant="ghost" aria-label={t("simulation.eventLog.back")} onClick={onClose}><X aria-hidden className="size-4" /></Button>
      </div>
      <nav aria-label={t("simulation.eventLog.steps")}>
        <ol className="sim-eventlog-steps">
          {STEPS.map((name, index) => {
            const locked = index >= 2 && !analysis;
            return (
              <li key={name}>
                <button type="button" aria-current={step === name ? "step" : undefined} disabled={locked} onClick={() => setStep(name)}>
                  <span aria-hidden>{index + 1}</span>{t(`simulation.eventLog.step.${name}`)}
                </button>
              </li>
            );
          })}
        </ol>
      </nav>

      {apply.isError && (
        <InlineNotice tone="error" title={t("simulation.eventLog.applyFailed")}>
          {httpErrorMessage(apply.error, t("simulation.eventLog.applyFailed"))}
        </InlineNotice>
      )}

      {step === "columns" && (
        <section className="sim-eventlog-step" aria-label={t("simulation.eventLog.step.columns")}>
          <TemplatePicker templates={templates.data ?? []} columns={columns} disabled={apply.isPending} onApply={applyTemplate} />
          {log.format === "csv" && <p className="sim-eventlog-hint">{t("simulation.eventLog.detectedSeparator", { separator: t(`simulation.eventLog.delimiterName.${delimiterKey(delimiter ?? log.delimiter ?? ",")}`) })}</p>}
          {log.format === "csv" && <details className="sim-eventlog-advanced" open={preview.isError}>
            <summary>{t("simulation.eventLog.correctSeparator")}</summary>
            <label className="sim-field">
              <span>{t("simulation.eventLog.delimiter")}</span>
              <select value={delimiter ?? log.delimiter ?? ""} onChange={(event) => { setDelimiter(event.target.value as Delimiter); setPage(0); }}>
                {DELIMITERS.map((value) => <option key={value} value={value}>{t(`simulation.eventLog.delimiterName.${delimiterKey(value)}`)}</option>)}
              </select>
            </label>
          </details>}
          {preview.isError && <InlineNotice tone="warning" title={httpErrorMessage(preview.error, t("simulation.eventLog.previewFailed"))} />}
          {preview.isPending && <Skeleton className="h-28 w-full" aria-hidden />}
          {preview.data && <>
            <div className="sim-eventlog-preview-head">
              <strong>{t("simulation.eventLog.fileRows", { count: preview.data.row_count })}</strong>
              {!showAllRows && preview.data.row_count > PREVIEW_ROWS && <Button size="sm" variant="outline" onClick={() => { setShowAllRows(true); setPage(0); }}>{t("simulation.eventLog.viewAll")}</Button>}
            </div>
            <PreviewTable columns={preview.data.columns} rows={preview.data.sample_rows} used={usedColumns(draft)} start={page * pageSize} />
            {showAllRows && preview.data.row_count > pageSize && <div className="sim-eventlog-pagination">
              <span>{t("simulation.eventLog.rowRange", { from: page * pageSize + 1, to: Math.min((page + 1) * pageSize, preview.data.row_count), total: preview.data.row_count })}</span>
              <Button size="sm" variant="outline" disabled={page === 0 || preview.isFetching} onClick={() => setPage((value) => value - 1)}>{t("simulation.eventLog.previousPage")}</Button>
              <Button size="sm" variant="outline" disabled={(page + 1) * pageSize >= preview.data.row_count || preview.isFetching} onClick={() => setPage((value) => value + 1)}>{t("simulation.eventLog.nextPage")}</Button>
            </div>}
          </>}
          <ColumnsForm draft={draft} columns={columns} onChange={update} />
          <div className="sim-eventlog-actions">
            <Button size="sm" onClick={() => setStep("formats")}>{t("simulation.eventLog.next")}</Button>
          </div>
        </section>
      )}

      {step === "formats" && (
        <section className="sim-eventlog-step" aria-label={t("simulation.eventLog.step.formats")}>
          <FormatsForm draft={draft} dateValues={dateValues} needsDateChoice={needsDateChoice} onDateConfirmed={() => setDateConfirmed(true)} onChange={update} />
          {issues.length > 0 && (
            <InlineNotice tone="warning" title={t("simulation.eventLog.incomplete")}>
              <ul>{issues.map((issue) => <li key={issue}>{t(`simulation.eventLog.issue.${issue}`)}</li>)}</ul>
            </InlineNotice>
          )}
          <div className="sim-eventlog-actions">
            <Button size="sm" variant="ghost" onClick={() => setStep("columns")}>{t("simulation.eventLog.previous")}</Button>
            <Button size="sm" disabled={issues.length > 0 || needsDateChoice || apply.isPending} onClick={() => run()}>
              {apply.isPending ? t("simulation.eventLog.applying") : t("simulation.eventLog.apply")}
            </Button>
          </div>
        </section>
      )}

      {/* Un log gia' mappato si apre sui risultati: finche' il report non c'e' lo si dice. */}
      {step !== "columns" && step !== "formats" && !analysis && (
        stored.isError ? (
          <InlineNotice
            tone="error"
            title={t("simulation.eventLog.analysisFailed")}
            action={<Button size="sm" variant="outline" onClick={() => setStep("columns")}>{t("simulation.eventLog.remap")}</Button>}
          >
            {httpErrorMessage(stored.error, t("simulation.eventLog.analysisFailed"))}
          </InlineNotice>
        ) : (
          <p className="sim-eventlog-hint" role="status">{t("simulation.eventLog.analysisLoading")}</p>
        )
      )}

      {step === "results" && analysis && (
        <ResultsStep analysis={analysis} draft={draft} templateId={templateId} columns={columns} onNext={() => setStep("activities")} />
      )}

      {step === "activities" && analysis && (
        <MatchStep
          key={`activities-${analysis.event_log.mapped_at}`}
          kind="activities"
          rows={analysis.activities.matches.map((m) => ({ key: m.activity, events: m.events, target: m.element_id, reason: m.reason }))}
          options={(model.data?.tasks ?? []).map((task) => ({ id: task.element_id, name: task.name }))}
          unobserved={analysis.activities.unobserved_elements.map((e) => e.name)}
          confirmed={analysis.activities.confirmed}
          noModel={analysis.activities.bpmn_version_id === null}
          pending={apply.isPending}
          onConfirm={(activityMatches) => run({ activityMatches })}
          onNext={() => setStep("resources")}
        />
      )}

      {step === "resources" && analysis && (
        <MatchStep
          key={`resources-${analysis.event_log.mapped_at}`}
          kind="resources"
          rows={analysis.resources.matches.map((m) => ({ key: m.resource, events: m.events, target: m.model_resource_id, reason: m.reason }))}
          options={(model.data?.resources ?? []).map((resource) => ({ id: resource.id, name: resource.name }))}
          unobserved={analysis.resources.unobserved_model_resources.map((r) => r.name)}
          confirmed={analysis.resources.confirmed}
          noModel={(model.data?.resources ?? []).length === 0}
          pending={apply.isPending}
          withoutResource={analysis.resources.events_without_resource}
          onConfirm={(resourceMatches) => run({ resourceMatches })}
          onNext={() => setStep("conformance")}
        />
      )}

      {step === "conformance" && analysis && (
        <ConformanceStep
          eventLogId={analysis.event_log.id}
          mappedAt={analysis.event_log.mapped_at}
          onDecorations={onDecorations}
          onReviewActivities={() => setStep("activities")}
          onNext={() => setStep("compare")}
        />
      )}

      {step === "compare" && analysis && (
        analysis.summary
          ? <RealVsSimulatedStep eventLogId={analysis.event_log.id} summary={analysis.summary} realCases={analysis.quality.cases} onDecorations={onDecorations} />
          : <InlineNotice tone="warning" title={t("simulation.eventLog.noKpis")} />
      )}
    </div>
  );
}

function TemplatePicker({ templates, columns, disabled, onApply }: {
  templates: EventLogTemplate[];
  columns: string[];
  disabled: boolean;
  onApply: (template: EventLogTemplate) => void;
}): React.JSX.Element | null {
  const { t } = useTranslation("process");
  const [chosen, setChosen] = React.useState("");
  if (templates.length === 0) return null;
  const template = templates.find((item) => String(item.id) === chosen) ?? null;
  const missing = template ? missingTemplateColumns(template.mapping, columns) : [];
  return (
    <div className="sim-eventlog-template">
      <label className="sim-field">
        <span>{t("simulation.eventLog.template")}</span>
        <select value={chosen} onChange={(event) => setChosen(event.target.value)}>
          <option value="">{t("simulation.eventLog.templateNone")}</option>
          {templates.map((item) => <option key={item.id} value={item.id}>{`${item.name} · v${item.version}`}</option>)}
        </select>
      </label>
      {missing.length > 0 && (
        <InlineNotice tone="warning" title={t("simulation.eventLog.templateMissing", { columns: missing.join(", ") })} />
      )}
      <Button size="sm" variant="outline" disabled={!template || missing.length > 0 || disabled} onClick={() => template && onApply(template)}>
        {t("simulation.eventLog.templateApply")}
      </Button>
    </div>
  );
}

function PreviewTable({ columns, rows, used, start }: { columns: string[]; rows: string[][]; used: Set<string>; start: number }): React.JSX.Element {
  const { t } = useTranslation("process");
  return (
    <div className="sim-eventlog-preview" role="region" aria-label={t("simulation.eventLog.preview")} tabIndex={0}>
      <table>
        <thead>
          <tr><th scope="col">#</th>{columns.map((column) => <th key={column} scope="col" data-used={used.has(column) || undefined}>{column}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, index) => <tr key={start + index}><th scope="row">{start + index + 2}</th>{columns.map((column, cellIndex) => <td key={column}>{row[cellIndex] ?? ""}</td>)}</tr>)}
        </tbody>
      </table>
    </div>
  );
}

function ColumnSelect({ label, hint, value, columns, optional, onChange }: {
  label: string;
  hint?: string;
  value: string;
  columns: string[];
  optional?: boolean;
  onChange: (value: string) => void;
}): React.JSX.Element {
  const { t } = useTranslation("process");
  const hintId = React.useId();
  return (
    <label className="sim-field">
      <span>{label}</span>
      <select value={value} aria-describedby={hint ? hintId : undefined} onChange={(event) => onChange(event.target.value)}>
        <option value="">{optional ? t("simulation.eventLog.notMapped") : t("simulation.eventLog.choose")}</option>
        {columns.map((column) => <option key={column} value={column}>{column}</option>)}
      </select>
      {hint && <small id={hintId}>{hint}</small>}
    </label>
  );
}

/** Una o piu' colonne unite (es. ordine + riga): si aggiungono una alla volta. */
function MultiColumn({ label, values, columns, onChange }: {
  label: string;
  values: string[];
  columns: string[];
  onChange: (values: string[]) => void;
}): React.JSX.Element {
  const { t } = useTranslation("process");
  return (
    <fieldset className="sim-eventlog-multi">
      <legend>{label}</legend>
      {values.length > 0 && (
        <ul>
          {values.map((value) => (
            <li key={value}>
              {value}
              <Button size="icon" variant="ghost" aria-label={t("simulation.eventLog.removeColumn", { column: value })} onClick={() => onChange(values.filter((item) => item !== value))}>
                <X aria-hidden className="size-3" />
              </Button>
            </li>
          ))}
        </ul>
      )}
      <label className="sim-field">
        <span className="sr-only">{t("simulation.eventLog.addColumnTo", { field: label })}</span>
        <select value="" onChange={(event) => event.target.value && onChange([...values, event.target.value])}>
          <option value="">{values.length ? t("simulation.eventLog.addColumn") : t("simulation.eventLog.choose")}</option>
          {columns.filter((column) => !values.includes(column)).map((column) => <option key={column} value={column}>{column}</option>)}
        </select>
      </label>
    </fieldset>
  );
}

function ColumnsForm({ draft, columns, onChange }: {
  draft: MappingDraft;
  columns: string[];
  onChange: (patch: Partial<MappingDraft>) => void;
}): React.JSX.Element {
  const { t } = useTranslation("process");
  return (
    <div className="sim-eventlog-form">
      <p className="sim-eventlog-hint">{t("simulation.eventLog.mappingHelp")}</p>
      <h3 className="sim-eventlog-title">{t("simulation.eventLog.requiredColumns")}</h3>
      <MultiColumn label={t("simulation.eventLog.field.caseId")} values={draft.caseId} columns={columns} onChange={(caseId) => onChange({ caseId })} />
      <p className="sim-eventlog-hint">{t("simulation.eventLog.caseHelp")}</p>
      <MultiColumn label={t("simulation.eventLog.field.activity")} values={draft.activity} columns={columns} onChange={(activity) => onChange({ activity })} />
      <p className="sim-eventlog-hint">{t("simulation.eventLog.activityHelp")}</p>
      <fieldset className="sim-eventlog-shape">
        <legend>{t("simulation.eventLog.field.timeShape")}</legend>
        {(["interval", "transition"] as const).map((shape) => (
          <label key={shape}>
            <input type="radio" name="time-shape" checked={draft.timeShape === shape} onChange={() => onChange({ timeShape: shape })} />
            {t(`simulation.eventLog.shape.${shape}`)}
          </label>
        ))}
      </fieldset>
      {draft.timeShape === "interval" ? (
        <>
          <ColumnSelect label={t("simulation.eventLog.field.end")} value={draft.end} columns={columns} onChange={(end) => onChange({ end })} />
          <ColumnSelect label={t("simulation.eventLog.field.start")} value={draft.start} columns={columns} optional onChange={(start) => onChange({ start })} />
          <ColumnSelect label={t("simulation.eventLog.field.enable")} hint={t("simulation.eventLog.field.enableHint")} value={draft.enable} columns={columns} optional onChange={(enable) => onChange({ enable })} />
        </>
      ) : (
        <>
          <ColumnSelect label={t("simulation.eventLog.field.timestamp")} value={draft.timestamp} columns={columns} onChange={(timestamp) => onChange({ timestamp })} />
          <ColumnSelect label={t("simulation.eventLog.field.lifecycle")} value={draft.lifecycle} columns={columns} optional onChange={(lifecycle) => onChange({ lifecycle })} />
        </>
      )}
      <details className="sim-eventlog-advanced">
        <summary>{t("simulation.eventLog.optionalColumns")}</summary>
        <ColumnSelect label={t("simulation.eventLog.field.resource")} value={draft.resource} columns={columns} optional onChange={(resource) => onChange({ resource })} />
        <ColumnSelect label={t("simulation.eventLog.field.role")} value={draft.role} columns={columns} optional onChange={(role) => onChange({ role })} />
        <ColumnSelect label={t("simulation.eventLog.field.cost")} value={draft.cost} columns={columns} optional onChange={(cost) => onChange({ cost })} />
        <AttributeList level="case" items={draft.caseAttributes} columns={columns} onChange={(caseAttributes) => onChange({ caseAttributes })} />
        <AttributeList level="event" items={draft.eventAttributes} columns={columns} onChange={(eventAttributes) => onChange({ eventAttributes })} />
      </details>
    </div>
  );
}

function AttributeList({ level, items, columns, onChange }: {
  level: "case" | "event";
  items: AttributeColumn[];
  columns: string[];
  onChange: (items: AttributeColumn[]) => void;
}): React.JSX.Element {
  const { t } = useTranslation("process");
  const patch = (index: number, value: Partial<AttributeColumn>) => onChange(items.map((item, i) => (i === index ? { ...item, ...value } : item)));
  return (
    <fieldset className="sim-eventlog-attributes">
      <legend>{t(`simulation.eventLog.attributes.${level}`)}</legend>
      {items.map((item, index) => (
        <div key={`${item.column}-${index}`} className="sim-eventlog-attribute">
          <span className="sim-eventlog-attribute-column">{item.column}</span>
          <label className="sim-field">
            <span>{t("simulation.eventLog.attributes.name")}</span>
            <input value={item.name} maxLength={64} onChange={(event) => patch(index, { name: event.target.value })} />
          </label>
          <label className="sim-field">
            <span>{t("simulation.eventLog.attributes.type")}</span>
            <select value={item.type} onChange={(event) => patch(index, { type: event.target.value as AttributeType })}>
              {ATTRIBUTE_TYPES.map((type) => <option key={type} value={type}>{t(`simulation.eventLog.attributes.typeName.${type}`)}</option>)}
            </select>
          </label>
          <Button size="icon" variant="ghost" aria-label={t("simulation.eventLog.removeColumn", { column: item.column })} onClick={() => onChange(items.filter((_, i) => i !== index))}>
            <X aria-hidden className="size-3" />
          </Button>
        </div>
      ))}
      <label className="sim-field">
        <span className="sr-only">{t(`simulation.eventLog.attributes.add.${level}`)}</span>
        <select value="" onChange={(event) => event.target.value && onChange(addAttribute(items, event.target.value))}>
          <option value="">{t(`simulation.eventLog.attributes.add.${level}`)}</option>
          {columns.map((column) => <option key={column} value={column}>{column}</option>)}
        </select>
      </label>
    </fieldset>
  );
}

function FormatsForm({ draft, dateValues, needsDateChoice, onDateConfirmed, onChange }: { draft: MappingDraft; dateValues: string[]; needsDateChoice: boolean; onDateConfirmed: () => void; onChange: (patch: Partial<MappingDraft>) => void }): React.JSX.Element {
  const { t } = useTranslation("process");
  return (
    <div className="sim-eventlog-form">
      <p className="sim-eventlog-hint">{t("simulation.eventLog.formatsHelp")}</p>
      <label className="sim-field">
        <span>{t("simulation.eventLog.field.pattern")}</span>
        <select value={needsDateChoice ? "__choose__" : draft.pattern} onChange={(event) => { onChange({ pattern: event.target.value }); onDateConfirmed(); }}>
          {needsDateChoice && <option value="__choose__">{t("simulation.eventLog.chooseDateFormat")}</option>}
          {!DATE_FORMATS.some((format) => format.value === draft.pattern) && <option value={draft.pattern}>{draft.pattern}</option>}
          {DATE_FORMATS.map((format) => <option key={format.value} value={format.value}>{format.sample}</option>)}
        </select>
        <small>{dateValues.find(Boolean) ? t("simulation.eventLog.dateExample", { value: dateValues.find(Boolean) }) : t("simulation.eventLog.noDateExample")}</small>
      </label>
      <details className="sim-eventlog-advanced">
        <summary>{t("simulation.eventLog.advancedFormats")}</summary>
        <label className="sim-field">
          <span>{t("simulation.eventLog.field.timezone")}</span>
          <select value={draft.timezone} onChange={(event) => onChange({ timezone: event.target.value })}>
            {(["Europe/Rome", "UTC", "Europe/London", "America/New_York", "America/Los_Angeles", "Asia/Dubai"] as const).map((zone) => <option key={zone} value={zone}>{zone}</option>)}
            {!(["Europe/Rome", "UTC", "Europe/London", "America/New_York", "America/Los_Angeles", "Asia/Dubai"] as string[]).includes(draft.timezone) && <option value={draft.timezone}>{draft.timezone}</option>}
          </select>
        </label>
        <label className="sim-field">
          <span>{t("simulation.eventLog.field.decimal")}</span>
          <select value={draft.decimal} onChange={(event) => onChange({ decimal: event.target.value as "." | "," })}>
            <option value=".">{t("simulation.eventLog.separator.dot")}</option>
            <option value=",">{t("simulation.eventLog.separator.comma")}</option>
          </select>
        </label>
        <label className="sim-field">
          <span>{t("simulation.eventLog.field.thousands")}</span>
          <select value={draft.thousands} onChange={(event) => onChange({ thousands: event.target.value as Thousands })}>
            <option value="">{t("simulation.eventLog.separator.none")}</option>
            <option value=".">{t("simulation.eventLog.separator.dot")}</option>
            <option value=",">{t("simulation.eventLog.separator.comma")}</option>
            <option value=" ">{t("simulation.eventLog.separator.space")}</option>
            <option value="'">{t("simulation.eventLog.separator.apostrophe")}</option>
          </select>
        </label>
      </details>
    </div>
  );
}

function ResultsStep({ analysis, draft, templateId, columns, onNext }: {
  analysis: EventLogAnalysis;
  draft: MappingDraft;
  templateId: number | null;
  columns: string[];
  onNext: () => void;
}): React.JSX.Element {
  const { t, i18n } = useTranslation("process");
  const lang = i18n.language?.startsWith("it") ? "it" : "en";
  const { quality, summary } = analysis;
  const save = useSaveEventLogTemplate();
  const [name, setName] = React.useState(analysis.event_log.template?.name ?? "");
  const baseTemplate = analysis.event_log.template;
  const saveAs = (templateKey?: string) =>
    save.mutate({ name: name.trim(), mapping: toColumnMapping(draft), columns, templateKey });
  return (
    <section className="sim-eventlog-step" aria-label={t("simulation.eventLog.step.results")}>
      <h3 className="sim-eventlog-title">{t("simulation.eventLog.quality")}</h3>
      <InlineNotice tone={quality.rows_excluded > 0 ? "warning" : undefined} title={quality.rows_excluded > 0 ? t("simulation.eventLog.qualityNeedsReview", { count: quality.rows_excluded }) : t("simulation.eventLog.qualityReady")}>{t("simulation.eventLog.qualitySummary", { read: quality.rows_read, used: quality.events })}</InlineNotice>
      <div className="sim-eventlog-tiles">
        <StatTile label={t("simulation.eventLog.kpi.events")} value={quality.events} hint={t("simulation.eventLog.kpi.rowsRead", { count: quality.rows_read })} />
        <StatTile label={t("simulation.eventLog.kpi.excluded")} value={quality.rows_excluded} tone={quality.rows_excluded > 0 ? "warning" : "ok"} />
        <StatTile label={t("simulation.eventLog.kpi.cases")} value={quality.cases} />
        <StatTile label={t("simulation.eventLog.kpi.activities")} value={quality.activities} />
      </div>
      {quality.period_start && quality.period_end && (
        <p className="sim-eventlog-hint">{t("simulation.eventLog.period", { from: formatDate(quality.period_start, lang), to: formatDate(quality.period_end, lang) })}</p>
      )}
      {quality.issues.length > 0 ? (
        <ul className="sim-eventlog-issues" aria-label={t("simulation.eventLog.issues")}>
          {quality.issues.map((issue) => (
            <li key={issue.code} data-excludes={issue.excludes_rows || undefined}>
              <strong>{issue.count}</strong> {t(`simulation.eventLog.qualityIssue.${issue.code}`, { defaultValue: issue.message })}
              <span>{t("simulation.eventLog.issueRows", { rows: issue.rows.join(", ") })}</span>
            </li>
          ))}
        </ul>
      ) : (
        <InlineNotice title={t("simulation.eventLog.noIssues")} />
      )}

      <h3 className="sim-eventlog-title">{t("simulation.eventLog.kpis")}</h3>
      {summary ? (
        <>
          {summary.timing !== "start_and_end" && (
            <InlineNotice tone="warning" title={t(`simulation.eventLog.timing.${summary.timing}`)} />
          )}
          <div className="sim-eventlog-tiles">
            <StatTile label={t("simulation.eventLog.kpi.cycle")} value={formatDuration(summary.cycle.avg, lang)} hint={`P90 ${formatDuration(summary.cycle.p90, lang)}`} />
            <StatTile label={t("simulation.eventLog.kpi.waiting")} value={formatDuration(summary.waiting.avg, lang)} />
            <StatTile label={t("simulation.eventLog.kpi.processing")} value={formatDuration(summary.processing.avg, lang)} />
            <StatTile label={t("simulation.eventLog.kpi.cost")} value={summary.cost ? summary.cost.total.toLocaleString(lang === "it" ? "it-IT" : "en-US", { maximumFractionDigits: 2 }) : t("simulation.eventLog.kpi.notInLog")} />
          </div>
        </>
      ) : (
        <InlineNotice tone="warning" title={t("simulation.eventLog.noKpis")} />
      )}

      <fieldset className="sim-eventlog-save">
        <legend>{t("simulation.eventLog.saveTemplate")}</legend>
        <label className="sim-field">
          <span>{t("simulation.eventLog.templateName")}</span>
          <input value={name} maxLength={120} onChange={(event) => setName(event.target.value)} />
        </label>
        <div className="sim-eventlog-actions">
          {baseTemplate && templateId === baseTemplate.id && (
            <Button size="sm" variant="outline" disabled={!name.trim() || save.isPending} onClick={() => saveAs(baseTemplate.template_key)}>
              {t("simulation.eventLog.saveVersion", { version: baseTemplate.version + 1 })}
            </Button>
          )}
          <Button size="sm" variant="outline" disabled={!name.trim() || save.isPending} onClick={() => saveAs()}>
            {t("simulation.eventLog.saveNew")}
          </Button>
        </div>
        {save.isSuccess && <InlineNotice title={t("simulation.eventLog.saved", { name: save.data.name, version: save.data.version })} />}
        {save.isError && <InlineNotice tone="error" title={httpErrorMessage(save.error, t("simulation.eventLog.saveFailed"))} />}
      </fieldset>

      <div className="sim-eventlog-actions">
        <Button size="sm" onClick={onNext}>{t("simulation.eventLog.next")}</Button>
      </div>
    </section>
  );
}

function formatDate(value: string, lang: "it" | "en"): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString(lang === "it" ? "it-IT" : "en-US", { day: "2-digit", month: "short", year: "numeric" });
}

type MatchRow = { key: string; events: number; target: string | null; reason: "same_name" | "ambiguous" | "none" };

/** Attivita' o risorse del log abbinate al modello: suggerite per nome identico, decise dal consulente. */
function MatchStep({ kind, rows, options, unobserved, confirmed, noModel, pending, withoutResource, onConfirm, onNext }: {
  kind: "activities" | "resources";
  rows: MatchRow[];
  options: { id: string; name: string }[];
  unobserved: string[];
  confirmed: boolean;
  noModel: boolean;
  pending: boolean;
  withoutResource?: number;
  onConfirm: (matches: Record<string, string | null>) => void;
  onNext?: () => void;
}): React.JSX.Element {
  const { t } = useTranslation("process");
  // Il genitore rimonta il passo a ogni esito nuovo (`key`): la scelta riparte dal report.
  const [choice, setChoice] = React.useState<Record<string, string | null>>(() =>
    Object.fromEntries(rows.map((row) => [row.key, row.target])),
  );
  const label = (key: string) => t(`simulation.eventLog.match.${kind}.choose`, { name: key });
  return (
    <section className="sim-eventlog-step" aria-label={t(`simulation.eventLog.step.${kind}`)}>
      <p className="sim-eventlog-hint">{t(`simulation.eventLog.match.${kind}.hint`)}</p>
      {noModel && <InlineNotice tone="warning" title={t(`simulation.eventLog.match.${kind}.noModel`)} />}
      {withoutResource ? <InlineNotice title={t("simulation.eventLog.match.resources.without", { count: withoutResource })} /> : null}
      {confirmed && <InlineNotice title={t("simulation.eventLog.match.confirmed")} />}
      <table className="sim-eventlog-matches">
        <thead>
          <tr>
            <th scope="col">{t(`simulation.eventLog.match.${kind}.log`)}</th>
            <th scope="col">{t("simulation.eventLog.match.events")}</th>
            <th scope="col">{t(`simulation.eventLog.match.${kind}.model`)}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key}>
              <th scope="row">
                {row.key}
                {row.reason === "ambiguous" && <small>{t("simulation.eventLog.match.ambiguous")}</small>}
              </th>
              <td>{row.events}</td>
              <td>
                <select aria-label={label(row.key)} value={choice[row.key] ?? ""} onChange={(event) => setChoice({ ...choice, [row.key]: event.target.value || null })}>
                  <option value="">{t("simulation.eventLog.match.ignore")}</option>
                  {options.map((option) => <option key={option.id} value={option.id}>{option.name}</option>)}
                </select>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {unobserved.length > 0 && (
        <InlineNotice tone="warning" title={t(`simulation.eventLog.match.${kind}.unobserved`, { count: unobserved.length })}>
          {unobserved.join(", ")}
        </InlineNotice>
      )}
      <div className="sim-eventlog-actions">
        <Button size="sm" disabled={pending || noModel} onClick={() => onConfirm(choice)}>
          {pending ? t("simulation.eventLog.applying") : t("simulation.eventLog.match.confirm")}
        </Button>
        {onNext && <Button size="sm" variant="ghost" onClick={onNext}>{t("simulation.eventLog.next")}</Button>}
      </div>
    </section>
  );
}
