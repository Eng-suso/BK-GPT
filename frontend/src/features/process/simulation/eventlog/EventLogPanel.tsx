import React from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Trash2, Upload, X } from "lucide-react";

import { EmptyState, InlineNotice } from "@/components/feedback";
import { StatTile } from "@/components/data";
import { httpErrorMessage } from "@/lib/http";
import { Button } from "@/ui/button";

import { fetchScenarioTemplate } from "../simulationApi";
import { formatDuration } from "../simulationResults";
import { useSimulationSection } from "../useSimulationSection";
import {
  addAttribute,
  draftFromMapping,
  draftIssues,
  emptyDraft,
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
import "./eventLog.css";

const STEPS = ["columns", "formats", "results", "activities", "resources"] as const;
type Step = (typeof STEPS)[number];
const PREVIEW_ROWS = 5;
const ACCEPT = ".csv,.tsv,.txt,.xes";

/** Import di un event log reale sul processo: file, mapping, qualita', KPI e abbinamenti al modello. */
export function EventLogPanel(): React.JSX.Element {
  const { t } = useTranslation("process");
  const { processId } = useSimulationSection();
  const logs = useEventLogs(processId);
  const upload = useUploadEventLog(processId);
  const remove = useDeleteEventLog(processId);
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [uploadDelimiter, setUploadDelimiter] = React.useState<Delimiter | "">("");
  const fileRef = React.useRef<HTMLInputElement>(null);
  const selected = logs.data?.find((log) => log.id === selectedId) ?? null;

  const onFile = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    upload.mutate(
      { file, delimiter: uploadDelimiter || undefined },
      { onSuccess: (log) => setSelectedId(log.id) },
    );
  };

  if (selected) {
    return <EventLogWizard key={selected.id} log={selected} onClose={() => setSelectedId(null)} />;
  }

  return (
    <div className="sim-eventlog">
      <p className="sim-eventlog-hint">{t("simulation.eventLog.intro")}</p>
      <div className="sim-eventlog-upload">
        <label className="sim-field">
          <span>{t("simulation.eventLog.delimiter")}</span>
          <select value={uploadDelimiter} onChange={(event) => setUploadDelimiter(event.target.value as Delimiter | "")}>
            <option value="">{t("simulation.eventLog.delimiterAuto")}</option>
            {DELIMITERS.map((value) => (
              <option key={value} value={value}>{t(`simulation.eventLog.delimiterName.${delimiterKey(value)}`)}</option>
            ))}
          </select>
        </label>
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
      {logs.isError && <InlineNotice tone="error" title={t("simulation.eventLog.loadFailed")} />}
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
              <Button size="icon" variant="ghost" aria-label={t("simulation.eventLog.delete", { name: log.name })} disabled={remove.isPending} onClick={() => remove.mutate(log.id)}>
                <Trash2 aria-hidden className="size-4" />
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function delimiterKey(value: string): string {
  return { ",": "comma", ";": "semicolon", "\t": "tab", "|": "pipe" }[value] ?? "comma";
}

function EventLogWizard({ log, onClose }: { log: EventLog; onClose: () => void }): React.JSX.Element {
  const { t } = useTranslation("process");
  const { processId, process } = useSimulationSection();
  const [step, setStep] = React.useState<Step>(log.status === "mapped" ? "results" : "columns");
  const [delimiter, setDelimiter] = React.useState<Delimiter | null>(null);
  const [draft, setDraft] = React.useState<MappingDraft>(() => (log.mapping ? draftFromMapping(log.mapping) : emptyDraft()));
  const [templateId, setTemplateId] = React.useState<number | null>(log.template?.id ?? null);
  const preview = useEventLogPreview(log.id, delimiter);
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
  const columns = preview.data?.columns ?? log.columns;
  const issues = draftIssues(draft);
  const update = (patch: Partial<MappingDraft>) => {
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
          {log.format === "csv" && (
            <label className="sim-field">
              <span>{t("simulation.eventLog.delimiter")}</span>
              <select value={delimiter ?? log.delimiter ?? ""} onChange={(event) => setDelimiter(event.target.value as Delimiter)}>
                {DELIMITERS.map((value) => (
                  <option key={value} value={value}>{t(`simulation.eventLog.delimiterName.${delimiterKey(value)}`)}</option>
                ))}
              </select>
            </label>
          )}
          {preview.isError && <InlineNotice tone="warning" title={httpErrorMessage(preview.error, t("simulation.eventLog.previewFailed"))} />}
          {preview.data && <PreviewTable columns={preview.data.columns} rows={preview.data.sample_rows.slice(0, PREVIEW_ROWS)} used={usedColumns(draft)} />}
          <ColumnsForm draft={draft} columns={columns} onChange={update} />
          <div className="sim-eventlog-actions">
            <Button size="sm" onClick={() => setStep("formats")}>{t("simulation.eventLog.next")}</Button>
          </div>
        </section>
      )}

      {step === "formats" && (
        <section className="sim-eventlog-step" aria-label={t("simulation.eventLog.step.formats")}>
          <FormatsForm draft={draft} onChange={update} />
          {issues.length > 0 && (
            <InlineNotice tone="warning" title={t("simulation.eventLog.incomplete")}>
              <ul>{issues.map((issue) => <li key={issue}>{t(`simulation.eventLog.issue.${issue}`)}</li>)}</ul>
            </InlineNotice>
          )}
          <div className="sim-eventlog-actions">
            <Button size="sm" variant="ghost" onClick={() => setStep("columns")}>{t("simulation.eventLog.previous")}</Button>
            <Button size="sm" disabled={issues.length > 0 || apply.isPending} onClick={() => run()}>
              {apply.isPending ? t("simulation.eventLog.applying") : t("simulation.eventLog.apply")}
            </Button>
          </div>
        </section>
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
        />
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

function PreviewTable({ columns, rows, used }: { columns: string[]; rows: string[][]; used: Set<string> }): React.JSX.Element {
  const { t } = useTranslation("process");
  return (
    <div className="sim-eventlog-preview" role="region" aria-label={t("simulation.eventLog.preview")} tabIndex={0}>
      <table>
        <thead>
          <tr>{columns.map((column) => <th key={column} scope="col" data-used={used.has(column) || undefined}>{column}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, index) => <tr key={index}>{row.map((cell, cellIndex) => <td key={cellIndex}>{cell}</td>)}</tr>)}
        </tbody>
      </table>
    </div>
  );
}

function ColumnSelect({ label, value, columns, optional, onChange }: {
  label: string;
  value: string;
  columns: string[];
  optional?: boolean;
  onChange: (value: string) => void;
}): React.JSX.Element {
  const { t } = useTranslation("process");
  return (
    <label className="sim-field">
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">{optional ? t("simulation.eventLog.notMapped") : t("simulation.eventLog.choose")}</option>
        {columns.map((column) => <option key={column} value={column}>{column}</option>)}
      </select>
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
      <MultiColumn label={t("simulation.eventLog.field.caseId")} values={draft.caseId} columns={columns} onChange={(caseId) => onChange({ caseId })} />
      <MultiColumn label={t("simulation.eventLog.field.activity")} values={draft.activity} columns={columns} onChange={(activity) => onChange({ activity })} />
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
        </>
      ) : (
        <>
          <ColumnSelect label={t("simulation.eventLog.field.timestamp")} value={draft.timestamp} columns={columns} onChange={(timestamp) => onChange({ timestamp })} />
          <ColumnSelect label={t("simulation.eventLog.field.lifecycle")} value={draft.lifecycle} columns={columns} optional onChange={(lifecycle) => onChange({ lifecycle })} />
        </>
      )}
      <ColumnSelect label={t("simulation.eventLog.field.resource")} value={draft.resource} columns={columns} optional onChange={(resource) => onChange({ resource })} />
      <ColumnSelect label={t("simulation.eventLog.field.role")} value={draft.role} columns={columns} optional onChange={(role) => onChange({ role })} />
      <ColumnSelect label={t("simulation.eventLog.field.cost")} value={draft.cost} columns={columns} optional onChange={(cost) => onChange({ cost })} />
      <AttributeList level="case" items={draft.caseAttributes} columns={columns} onChange={(caseAttributes) => onChange({ caseAttributes })} />
      <AttributeList level="event" items={draft.eventAttributes} columns={columns} onChange={(eventAttributes) => onChange({ eventAttributes })} />
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

function FormatsForm({ draft, onChange }: { draft: MappingDraft; onChange: (patch: Partial<MappingDraft>) => void }): React.JSX.Element {
  const { t } = useTranslation("process");
  return (
    <div className="sim-eventlog-form">
      <label className="sim-field">
        <span>{t("simulation.eventLog.field.pattern")}</span>
        <input value={draft.pattern} placeholder="%d/%m/%Y %H:%M" onChange={(event) => onChange({ pattern: event.target.value })} aria-describedby="eventlog-pattern-hint" />
        <small id="eventlog-pattern-hint">{t("simulation.eventLog.field.patternHint")}</small>
      </label>
      <label className="sim-field">
        <span>{t("simulation.eventLog.field.timezone")}</span>
        <input value={draft.timezone} onChange={(event) => onChange({ timezone: event.target.value })} />
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
