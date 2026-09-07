import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { AlertTriangle } from "lucide-react";

import { Field, FormDialog } from "@/components/form";
import { Input } from "@/ui/input";
import { Textarea } from "@/ui/textarea";
import { httpErrorMessage } from "@/lib/http";
import {
  useArchiveRecordMutation,
  useDeleteRecordMutation,
  useRecordImpactQuery,
  useRestoreRecordMutation,
  type RecordKind,
} from "./api";
import type { ArchiveImpact } from "@/contracts/workspace";

export type LifecycleAction = "archive" | "restore" | "delete";

export type LifecycleTarget = {
  kind: RecordKind;
  id: string;
  name: string;
};

type RecordLifecycleDialogProps = {
  /** `null` tiene il dialog chiuso. */
  target: LifecycleTarget | null;
  action: LifecycleAction;
  onOpenChange: (open: boolean) => void;
  onDone?: () => void;
};

/**
 * Chiudere, riaprire o eliminare un record del workspace.
 *
 * Le tre operazioni condividono un dialog perche' condividono la domanda a cui
 * il consulente deve rispondere — cosa succede ai record collegati — ma non il
 * peso: archiviare chiede un motivo facoltativo, eliminare chiede di scrivere
 * il nome, e in entrambi i casi l'impatto e' contato dal backend, non stimato
 * qui. Un "sei sicuro?" senza numeri non e' una conferma informata.
 */
export function RecordLifecycleDialog({
  target,
  action,
  onOpenChange,
  onDone,
}: RecordLifecycleDialogProps): React.JSX.Element | null {
  const { t } = useTranslation("common");
  const [reason, setReason] = useState("");
  const [typedName, setTypedName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const impactQuery = useRecordImpactQuery(
    target?.kind ?? "client",
    action === "restore" ? null : (target?.id ?? null),
  );
  const archive = useArchiveRecordMutation();
  const restore = useRestoreRecordMutation();
  const remove = useDeleteRecordMutation();

  if (!target) return null;

  const isSubmitting =
    archive.isPending || restore.isPending || remove.isPending;
  const nameMatches = typedName.trim() === target.name.trim();

  const submit = () => {
    setError(null);
    const onError = (cause: unknown) =>
      setError(httpErrorMessage(cause, t("lifecycle.error")));
    const done = (message: string) => {
      toast.success(message);
      onOpenChange(false);
      onDone?.();
    };

    if (action === "archive") {
      archive.mutate(
        { kind: target.kind, id: target.id, reason },
        {
          onSuccess: () => done(t("lifecycle.toast.archived", { name: target.name })),
          onError,
        },
      );
      return;
    }

    if (action === "restore") {
      restore.mutate(
        { kind: target.kind, id: target.id },
        {
          onSuccess: () => done(t("lifecycle.toast.restored", { name: target.name })),
          onError,
        },
      );
      return;
    }

    if (!nameMatches) {
      setError(t("lifecycle.delete.nameMismatch"));
      return;
    }
    remove.mutate(
      { kind: target.kind, id: target.id },
      {
        onSuccess: () => done(t("lifecycle.toast.deleted", { name: target.name })),
        onError,
      },
    );
  };

  const kindLabel = t(`lifecycle.kind.${target.kind}`);

  return (
    <FormDialog
      open
      onOpenChange={onOpenChange}
      title={t(`lifecycle.${action}.title`, { kind: kindLabel })}
      description={t(`lifecycle.${action}.description`, { name: target.name })}
      submitLabel={t(`lifecycle.${action}.submit`)}
      isSubmitting={isSubmitting}
      error={error}
      onSubmit={submit}
    >
      {action !== "restore" ? (
        <ImpactSummary
          impact={impactQuery.data}
          isLoading={impactQuery.isLoading}
          destructive={action === "delete"}
        />
      ) : null}

      {action === "archive" ? (
        <Field label={t("lifecycle.archive.reason")} hint={t("lifecycle.archive.reasonHint")}>
          {(props) => (
            <Textarea
              {...props}
              rows={3}
              value={reason}
              placeholder={t("lifecycle.archive.reasonPlaceholder")}
              onChange={(event) => setReason(event.target.value)}
            />
          )}
        </Field>
      ) : null}

      {action === "delete" ? (
        <Field
          label={t("lifecycle.delete.confirmLabel", { name: target.name })}
          hint={t("lifecycle.delete.confirmHint")}
          required
        >
          {(props) => (
            <Input
              {...props}
              value={typedName}
              autoFocus
              autoComplete="off"
              onChange={(event) => setTypedName(event.target.value)}
            />
          )}
        </Field>
      ) : null}
    </FormDialog>
  );
}

/** I record collegati, contati dal backend. */
function ImpactSummary({
  impact,
  isLoading,
  destructive,
}: {
  impact: ArchiveImpact | undefined;
  isLoading: boolean;
  destructive: boolean;
}): React.JSX.Element {
  const { t } = useTranslation("common");

  if (isLoading || !impact) {
    return (
      <p className="text-xs text-muted-foreground">{t("state.loading")}</p>
    );
  }

  const rows: { label: string; value: number }[] = [
    { label: t("lifecycle.impact.projects"), value: impact.projects },
    { label: t("lifecycle.impact.processes"), value: impact.processes },
    { label: t("lifecycle.impact.sources"), value: impact.sources },
    { label: t("lifecycle.impact.decisions"), value: impact.decisions },
  ].filter((row) => row.value > 0);

  return (
    <section
      className="flex flex-col gap-2 rounded-lg border border-border bg-muted/40 p-3"
      aria-label={t("lifecycle.impact.title")}
    >
      <p className="text-[11px] font-semibold uppercase tracking-[0.04em] text-muted-foreground">
        {t("lifecycle.impact.title")}
      </p>
      {rows.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          {t("lifecycle.impact.none")}
        </p>
      ) : (
        <ul className="flex flex-col gap-1 text-xs text-foreground">
          {rows.map((row) => (
            <li key={row.label} className="flex items-center justify-between gap-3">
              <span>{row.label}</span>
              <span className="tabular-nums font-semibold">{row.value}</span>
            </li>
          ))}
        </ul>
      )}
      {destructive ? (
        <p className="flex items-start gap-1.5 text-xs text-[var(--color-status-danger)]">
          <AlertTriangle className="mt-0.5 size-3.5 flex-none" aria-hidden="true" />
          {t("lifecycle.delete.warning")}
        </p>
      ) : null}
    </section>
  );
}
