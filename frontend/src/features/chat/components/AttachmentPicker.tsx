import React, { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { ChevronRight, Search } from "lucide-react";

import { Button } from "@/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/ui/dialog";
import { Input } from "@/ui/input";
import { Textarea } from "@/ui/textarea";
import { Skeleton } from "@/ui/skeleton";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import {
  useProjectQuery,
  useProjectSourcesQuery,
  useProjectsQuery,
} from "@/features/projects/api";
import { listProsimosSimulationRuns } from "@/features/process/simulation/simulationApi";
import {
  MAX_NOTE_ATTACHMENT_CHARS,
  type ChatAttachment,
  type ChatAttachmentKind,
} from "../../../contracts/chat";
import type { ChatScope } from "../chatScope";

type AttachmentPickerProps = {
  /** Which kind the consultant asked for; `null` keeps the dialog closed. */
  kind: ChatAttachmentKind | null;
  scope: ChatScope;
  onPick: (attachment: ChatAttachment) => void;
  onClose: () => void;
};

/** What the picker still needs before it can list anything. */
type Selection = { projectId?: string; bpmnModelId?: string };

type Row = { id: string; label: string; meta?: string };

/**
 * Derives the initial attachment selection from the current chat scope.
 *
 * @param scope - The chat scope used to initialize project and process selections
 * @returns The corresponding project and BPMN model identifiers
 */
function scopeSelection(scope: ChatScope): Selection {
  if (scope.type === "canvas") {
    return { projectId: scope.projectId, bpmnModelId: scope.bpmnModelId };
  }
  if (scope.type === "process" || scope.type === "project") {
    return { projectId: scope.projectId };
  }
  return {};
}

/**
 * Determines whether a row matches a search query using its label and metadata.
 *
 * @param row - The row to search
 * @param query - The search text
 * @returns `true` if the query is empty or appears in the row's label or metadata, `false` otherwise.
 */
function matches(row: Row, query: string): boolean {
  if (!query.trim()) return true;
  const needle = query.trim().toLowerCase();
  return `${row.label} ${row.meta ?? ""}`.toLowerCase().includes(needle);
}

/**
 * Scegliere cosa allegare, partendo da dove si e'.
 *
 * Non e' un file picker: si sceglie fra gli oggetti che il workspace conosce
 * gia'. Se lo scope dice gia' il progetto (o il modello), il passaggio sparisce;
 * dalla chat consulente, che non ha progetto, il primo passo e' sceglierlo.
 */
export const AttachmentPicker: React.FC<AttachmentPickerProps> = ({
  kind,
  scope,
  onPick,
  onClose,
}) => {
  const { t } = useTranslation("chat");
  const [selection, setSelection] = useState<Selection>(() => scopeSelection(scope));
  const [query, setQuery] = useState("");
  const [noteText, setNoteText] = useState("");

  // Riaprire il picker deve ripartire dallo scope corrente, non dall'ultimo
  // giro: `kind` che torna non-null e' l'apertura.
  const [openedFor, setOpenedFor] = useState<ChatAttachmentKind | null>(null);
  if (kind && kind !== openedFor) {
    setOpenedFor(kind);
    setSelection(scopeSelection(scope));
    setQuery("");
    setNoteText("");
  }
  if (!kind && openedFor) setOpenedFor(null);

  const needsProject = kind !== "note" && !selection.projectId;
  const needsProcess =
    kind === "simulation_run" && !!selection.projectId && !selection.bpmnModelId;

  const projects = useProjectsQuery();
  const project = useProjectQuery(selection.projectId ?? "");
  const sources = useProjectSourcesQuery(selection.projectId ?? "");
  const runs = useQuery({
    queryKey: ["simulation-runs", selection.bpmnModelId ?? ""],
    queryFn: () => listProsimosSimulationRuns(selection.bpmnModelId ?? ""),
    enabled: kind === "simulation_run" && !!selection.bpmnModelId,
  });

  const step = useMemo(() => {
    if (kind === "note") return "note" as const;
    if (needsProject) return "project" as const;
    if (needsProcess) return "process" as const;
    if (kind === "source") return "source" as const;
    if (kind === "process") return "process" as const;
    return "run" as const;
  }, [kind, needsProject, needsProcess]);

  const active =
    step === "project"
      ? projects
      : step === "source"
        ? sources
        : step === "run"
          ? runs
          : project;

  const rows: Row[] = useMemo(() => {
    if (step === "project") {
      return (projects.data ?? []).map((item) => ({
        id: item.id,
        label: item.name,
        meta: item.client,
      }));
    }
    if (step === "process") {
      return (project.data?.processItems ?? []).map((item) => ({
        id: item.id,
        label: item.name,
        meta: `${item.stage} · ${item.status}`,
      }));
    }
    if (step === "source") {
      return (sources.data ?? []).map((item) => ({
        id: item.id,
        label: item.name,
        meta: item.type,
      }));
    }
    return (runs.data ?? [])
      .filter((run) => run.status === "completed")
      .map((run) => ({
        id: String(run.id),
        label: run.scenario_name,
        meta: new Date(run.created_at).toLocaleString(),
      }));
  }, [step, projects.data, project.data, sources.data, runs.data]);

  const visible = rows.filter((row) => matches(row, query));

  const handleRow = (row: Row) => {
    if (step === "project") {
      setSelection({ projectId: row.id });
      setQuery("");
      return;
    }

    if (step === "process") {
      const process = (project.data?.processItems ?? []).find((item) => item.id === row.id);

      // Allegare un processo per parlarne e' una cosa; sceglierlo per arrivare
      // alle sue run e' un passaggio intermedio.
      if (kind === "simulation_run") {
        if (process) setSelection((prev) => ({ ...prev, bpmnModelId: process.bpmnModelId }));
        setQuery("");
        return;
      }

      onPick({
        kind: "process",
        id: row.id,
        label: row.label,
        projectId: selection.projectId ?? "",
      });
      return;
    }

    if (step === "source") {
      onPick({
        kind: "source",
        id: row.id,
        label: row.label,
        projectId: selection.projectId ?? "",
      });
      return;
    }

    onPick({
      kind: "simulation_run",
      id: row.id,
      label: row.label,
      bpmnModelId: selection.bpmnModelId ?? "",
    });
  };

  const submitNote = () => {
    const text = noteText.trim();
    if (!text) return;

    const firstLine = text.split("\n")[0]?.trim() ?? "";
    onPick({
      kind: "note",
      // Il testo incollato non ha un id nel workspace: ne serve uno solo per
      // distinguere due note nella stessa riga.
      id: `note-${Date.now()}`,
      label: firstLine.length > 48 ? `${firstLine.slice(0, 48)}…` : firstLine || t("attach.note.fallbackLabel"),
      text: text.slice(0, MAX_NOTE_ATTACHMENT_CHARS),
    });
  };

  return (
    <Dialog open={kind !== null} onOpenChange={(next) => { if (!next) onClose(); }}>
      <DialogContent
        className="attachment-picker flex max-h-[70dvh] flex-col overflow-hidden border-border sm:max-w-lg"
        aria-describedby="attachment-picker-help"
      >
        <DialogTitle>{t(`attach.${kind ?? "source"}.title`)}</DialogTitle>
        <DialogDescription id="attachment-picker-help">
          {t(`attach.step.${step}`)}
        </DialogDescription>

        {step === "note" ? (
          <>
            <Textarea
              autoFocus
              rows={10}
              value={noteText}
              onChange={(event) => setNoteText(event.target.value)}
              maxLength={MAX_NOTE_ATTACHMENT_CHARS}
              placeholder={t("attach.note.placeholder")}
              aria-label={t("attach.note.placeholder")}
              className="min-h-[220px] resize-none"
            />
            <div className="flex items-center justify-between gap-3">
              <span className="text-xs text-muted-foreground" aria-live="polite">
                {t("attach.note.count", {
                  count: noteText.length,
                  max: MAX_NOTE_ATTACHMENT_CHARS,
                })}
              </span>
              <Button type="button" size="sm" disabled={!noteText.trim()} onClick={submitNote}>
                {t("attach.note.confirm")}
              </Button>
            </div>
          </>
        ) : (
          <>
            <div className="relative">
              <Search
                className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
                aria-hidden="true"
              />
              <Input
                autoFocus
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder={t("attach.search")}
                aria-label={t("attach.search")}
                className="pl-9"
              />
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto">
              {active.isPending ? (
                <div className="flex flex-col gap-2 py-1">
                  <Skeleton className="h-11 w-full" />
                  <Skeleton className="h-11 w-full" />
                  <Skeleton className="h-11 w-full" />
                </div>
              ) : active.isError ? (
                <ErrorState
                  title={t("attach.error")}
                  onRetry={() => void active.refetch()}
                />
              ) : visible.length === 0 ? (
                <EmptyState variant="inline" title={t("attach.empty")} />
              ) : (
                <ul className="flex flex-col gap-1">
                  {visible.map((row) => (
                    <li key={row.id}>
                      <button
                        type="button"
                        className="attachment-picker-row"
                        onClick={() => handleRow(row)}
                      >
                        <span className="attachment-picker-row-text">
                          <span className="attachment-picker-row-label">{row.label}</span>
                          {row.meta && (
                            <span className="attachment-picker-row-meta">{row.meta}</span>
                          )}
                        </span>
                        <ChevronRight className="size-4 opacity-50" aria-hidden="true" />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
};
