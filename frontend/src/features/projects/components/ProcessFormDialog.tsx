import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { Field, FormDialog, VocabularySelect } from "@/components/form";
import { Input } from "@/ui/input";
import { Meter } from "@/components/data";
import {
  PROCESS_STAGES,
  PROCESS_STATUSES,
  type ProcessDraft,
} from "@/contracts/workspace";
import { httpErrorMessage } from "@/lib/http";
import { useCreateProcessMutation, useUpdateProcessMutation } from "../api";
import type { ProjectProcess } from "../types";

const EMPTY: ProcessDraft = {
  name: "",
  stage: "AS-IS",
  status: "Bozza",
  owner: "",
  readiness: 0,
};

function draftFrom(process: ProjectProcess | null): ProcessDraft {
  if (!process) return EMPTY;
  return {
    name: process.name,
    stage: process.stage,
    status: process.status,
    owner: process.owner,
    readiness: process.readiness,
  };
}

type ProcessFormDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Progetto che ospita il processo: serve alla creazione. */
  projectId: string;
  /** `null` crea, un processo modifica quel record. */
  process: ProjectProcess | null;
};

/**
 * Il record di processo, modificabile a mano.
 *
 * Creare qui non disegna niente: nasce il record e il suo modello BPMN vuoto,
 * che si riempie nel canvas o con l'agente. Stadio e stato rispondono a due
 * domande diverse — quale processo si sta descrivendo, e quanto e' avanti
 * quella descrizione — e ognuno porta la propria definizione nel menu.
 *
 * Come gli altri form del workspace, la bozza nasce al montaggio: chi apre il
 * dialog gli passa una `key` nuova a ogni apertura.
 */
export function ProcessFormDialog({
  open,
  onOpenChange,
  projectId,
  process,
}: ProcessFormDialogProps): React.JSX.Element {
  const { t } = useTranslation("projects");
  const [draft, setDraft] = useState<ProcessDraft>(() => draftFrom(process));
  const [error, setError] = useState<string | null>(null);

  const create = useCreateProcessMutation(projectId);
  const update = useUpdateProcessMutation();
  const isSubmitting = create.isPending || update.isPending;

  const set = <K extends keyof ProcessDraft>(key: K, value: ProcessDraft[K]) =>
    setDraft((current) => ({ ...current, [key]: value }));

  const submit = () => {
    if (!draft.name.trim()) {
      setError(t("process.form.error.nameRequired"));
      return;
    }
    setError(null);

    const onError = (cause: unknown) =>
      setError(httpErrorMessage(cause, t("process.form.error.save")));
    const onSuccess = (saved: ProjectProcess) => {
      toast.success(
        process
          ? t("process.form.toast.updated", { name: saved.name })
          : t("process.form.toast.created", { name: saved.name }),
      );
      onOpenChange(false);
    };

    if (process) {
      update.mutate({ id: process.id, draft }, { onSuccess, onError });
    } else {
      create.mutate(draft, { onSuccess, onError });
    }
  };

  return (
    <FormDialog
      open={open}
      onOpenChange={onOpenChange}
      title={process ? t("process.form.editTitle") : t("process.form.createTitle")}
      description={
        process ? t("process.form.editDescription") : t("process.form.createDescription")
      }
      submitLabel={process ? t("form.save") : t("process.form.create")}
      isSubmitting={isSubmitting}
      error={error}
      onSubmit={submit}
    >
      <Field label={t("process.form.fields.name")} required>
        {(props) => (
          <Input
            {...props}
            value={draft.name}
            autoFocus
            placeholder={t("process.form.placeholder.name")}
            onChange={(event) => set("name", event.target.value)}
          />
        )}
      </Field>

      <div className="grid gap-5 sm:grid-cols-2">
        <Field
          label={t("process.form.fields.stage")}
          hint={t("process.form.hint.stage")}
        >
          {(props) => (
            <VocabularySelect
              {...props}
              value={draft.stage}
              onChange={(value) => set("stage", value as ProcessDraft["stage"])}
              options={PROCESS_STAGES.map((stage) => ({
                value: stage,
                label: stage,
                meaning: t(`vocab.processStage.${stage}`),
              }))}
            />
          )}
        </Field>

        <Field
          label={t("process.form.fields.status")}
          hint={t("process.form.hint.status")}
        >
          {(props) => (
            <VocabularySelect
              {...props}
              value={draft.status}
              onChange={(value) => set("status", value as ProcessDraft["status"])}
              options={PROCESS_STATUSES.map((status) => ({
                value: status,
                label: status,
                meaning: t(`vocab.processStatus.${status}`),
              }))}
            />
          )}
        </Field>
      </div>

      <Field label={t("process.form.fields.owner")} hint={t("process.form.hint.owner")}>
        {(props) => (
          <Input
            {...props}
            value={draft.owner}
            placeholder={t("process.form.placeholder.owner")}
            onChange={(event) => set("owner", event.target.value)}
          />
        )}
      </Field>

      <Field
        label={t("process.form.fields.readiness")}
        hint={t("process.form.hint.readiness")}
      >
        {(props) => (
          <div className="flex items-center gap-3">
            <Input
              {...props}
              type="number"
              min={0}
              max={100}
              step={5}
              inputMode="numeric"
              className="w-24 tabular-nums"
              value={String(draft.readiness)}
              onChange={(event) =>
                set(
                  "readiness",
                  Math.max(0, Math.min(100, Number(event.target.value) || 0)),
                )
              }
            />
            <Meter value={draft.readiness} showValue={false} className="flex-1" />
          </div>
        )}
      </Field>
    </FormDialog>
  );
}
