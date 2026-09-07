import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import {
  Field,
  FormDialog,
  ListField,
  VocabularySelect,
} from "@/components/form";
import { Input } from "@/ui/input";
import { Textarea } from "@/ui/textarea";
import { Meter } from "@/components/data";
import {
  PROJECT_PHASES,
  PROJECT_STATUSES,
  type ProjectDraft,
} from "@/contracts/workspace";
import { httpErrorMessage } from "@/lib/http";
import { useClientsQuery } from "@/features/clients/api";
import { useCreateProjectMutation, useUpdateProjectMutation } from "../api";
import type { Project } from "../types";

const EMPTY: ProjectDraft = {
  clientId: "",
  name: "",
  objective: "",
  phase: "Discovery",
  status: "Bozza",
  progress: 0,
  nextStep: "",
  milestones: [],
  openIssues: [],
  deliverables: [],
};

function draftFrom(project: Project | null, clientId: string): ProjectDraft {
  if (!project) return { ...EMPTY, clientId };
  return {
    clientId: project.clientId,
    name: project.name,
    objective: project.objective,
    phase: project.phase,
    status: project.status,
    progress: project.progress,
    nextStep: project.nextStep,
    milestones: project.milestones,
    openIssues: project.openIssues,
    deliverables: project.deliverables,
  };
}

type ProjectFormDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** `null` crea, un progetto modifica quel record. */
  project: Project | null;
  /** Cliente preselezionato quando si crea da un contesto che lo conosce gia'. */
  defaultClientId?: string;
};

/**
 * Il record di progetto, modificabile a mano.
 *
 * L'obiettivo sta in cima e non in fondo: e' il perche' dell'incarico, l'unico
 * campo che una Project Chat aperta domani legge come proprio mandato, e finche'
 * e' vuoto il progetto e' un contenitore senza motivo (PROJECT-01). Fase e stato
 * non sono testo libero: sono lo stesso vocabolario che vede l'agente, con la
 * definizione di ogni voce accanto.
 *
 * La bozza nasce dal record al montaggio e basta: chi apre il dialog gli passa
 * una `key` nuova a ogni apertura, cosi' la riapertura riparte dai dati veri
 * invece di risincronizzare lo state dentro un effetto.
 */
export function ProjectFormDialog({
  open,
  onOpenChange,
  project,
  defaultClientId = "",
}: ProjectFormDialogProps): React.JSX.Element {
  const { t } = useTranslation("projects");
  const [draft, setDraft] = useState<ProjectDraft>(() =>
    draftFrom(project, defaultClientId),
  );
  const [error, setError] = useState<string | null>(null);

  const clientsQ = useClientsQuery();
  const clients = clientsQ.data ?? [];
  const create = useCreateProjectMutation();
  const update = useUpdateProjectMutation();
  const isSubmitting = create.isPending || update.isPending;

  const set = <K extends keyof ProjectDraft>(key: K, value: ProjectDraft[K]) =>
    setDraft((current) => ({ ...current, [key]: value }));

  const submit = () => {
    if (!draft.clientId) {
      setError(t("form.error.clientRequired"));
      return;
    }
    if (!draft.name.trim()) {
      setError(t("form.error.nameRequired"));
      return;
    }
    setError(null);

    const onError = (cause: unknown) =>
      setError(httpErrorMessage(cause, t("form.error.save")));
    const onSuccess = (saved: Project) => {
      toast.success(
        project
          ? t("form.toast.updated", { name: saved.name })
          : t("form.toast.created", { name: saved.name }),
      );
      onOpenChange(false);
    };

    if (project) {
      update.mutate({ id: project.id, draft }, { onSuccess, onError });
    } else {
      create.mutate(draft, { onSuccess, onError });
    }
  };

  return (
    <FormDialog
      open={open}
      onOpenChange={onOpenChange}
      title={project ? t("form.editTitle") : t("form.createTitle")}
      description={t("form.description")}
      submitLabel={project ? t("form.save") : t("form.create")}
      isSubmitting={isSubmitting}
      error={error}
      onSubmit={submit}
      className="sm:max-w-2xl"
    >
      <Field label={t("form.fields.name")} required>
        {(props) => (
          <Input
            {...props}
            value={draft.name}
            autoFocus
            onChange={(event) => set("name", event.target.value)}
          />
        )}
      </Field>

      <Field
        label={t("form.fields.client")}
        required
        hint={clientsQ.isError ? t("form.hint.clientsUnavailable") : undefined}
      >
        {(props) => (
          <VocabularySelect
            {...props}
            value={draft.clientId}
            onChange={(value) => set("clientId", value)}
            placeholder={t("form.placeholder.client")}
            options={clients.map((client) => ({
              value: client.id,
              label: client.name,
              meaning: `${client.sector} · ${client.status}`,
            }))}
          />
        )}
      </Field>

      <Field
        label={t("form.fields.objective")}
        hint={t("form.hint.objective")}
      >
        {(props) => (
          <Textarea
            {...props}
            value={draft.objective}
            rows={4}
            placeholder={t("form.placeholder.objective")}
            onChange={(event) => set("objective", event.target.value)}
          />
        )}
      </Field>

      <div className="grid gap-5 sm:grid-cols-2">
        <Field label={t("form.fields.phase")} hint={t("form.hint.phase")}>
          {(props) => (
            <VocabularySelect
              {...props}
              value={draft.phase}
              onChange={(value) => set("phase", value)}
              options={PROJECT_PHASES.map((phase) => ({
                value: phase,
                label: phase,
                meaning: t(`vocab.phase.${phase}`),
              }))}
            />
          )}
        </Field>

        <Field label={t("form.fields.status")} hint={t("form.hint.status")}>
          {(props) => (
            <VocabularySelect
              {...props}
              value={draft.status}
              onChange={(value) => set("status", value as ProjectDraft["status"])}
              options={PROJECT_STATUSES.map((status) => ({
                value: status,
                label: status,
                meaning: t(`vocab.status.${status}`),
              }))}
            />
          )}
        </Field>
      </div>

      <Field label={t("form.fields.progress")}>
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
              value={String(draft.progress)}
              onChange={(event) =>
                set(
                  "progress",
                  Math.max(0, Math.min(100, Number(event.target.value) || 0)),
                )
              }
            />
            <Meter value={draft.progress} showValue={false} className="flex-1" />
          </div>
        )}
      </Field>

      <Field label={t("form.fields.nextStep")} hint={t("form.hint.nextStep")}>
        {(props) => (
          <Input
            {...props}
            value={draft.nextStep}
            placeholder={t("form.placeholder.nextStep")}
            onChange={(event) => set("nextStep", event.target.value)}
          />
        )}
      </Field>

      <ListField
        label={t("form.fields.milestones")}
        values={draft.milestones}
        onChange={(values) => set("milestones", values)}
        addLabel={t("form.list.add")}
        removeLabel={t("form.list.remove")}
        emptyLabel={t("form.list.emptyMilestones")}
      />

      <ListField
        label={t("form.fields.deliverables")}
        values={draft.deliverables}
        onChange={(values) => set("deliverables", values)}
        addLabel={t("form.list.add")}
        removeLabel={t("form.list.remove")}
        emptyLabel={t("form.list.emptyDeliverables")}
      />

      <ListField
        label={t("form.fields.openIssues")}
        values={draft.openIssues}
        onChange={(values) => set("openIssues", values)}
        addLabel={t("form.list.add")}
        removeLabel={t("form.list.remove")}
        emptyLabel={t("form.list.emptyOpenIssues")}
      />
    </FormDialog>
  );
}
