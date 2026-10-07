import React, { useId, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/ui/dialog";
import { useProjectsQuery } from "@/features/projects/api";
import type { UploadDestination } from "../hooks/useComposerUploads";

/** Il valore della voce "Tutto il cliente": gli id dei processi non hanno spazi. */
const CLIENT_SCOPE = "whole client";

type UploadDestinationDialogProps = {
  open: boolean;
  /** L'ultima destinazione scelta: si riparte da li'. */
  initial: UploadDestination | null;
  onConfirm: (destination: UploadDestination) => void;
  onClose: () => void;
};

/**
 * Dove va un file caricato dalla chat del consulente.
 *
 * La chat del consulente non ha un progetto: prima di caricare si sceglie il
 * progetto e, se serve, il processo. Un file messo in un processo diventa
 * evidenza di quel processo; messo nel progetto, contesto. Messo nel cliente
 * del progetto (P1.16), vale per tutti i suoi progetti.
 */
export function UploadDestinationDialog({
  open,
  initial,
  onConfirm,
  onClose,
}: UploadDestinationDialogProps): React.JSX.Element {
  const { t } = useTranslation("chat");
  const projects = useProjectsQuery();
  const [projectId, setProjectId] = useState(initial?.projectId ?? "");
  const [processId, setProcessId] = useState(initial?.processId ?? "");
  const [wholeClient, setWholeClient] = useState(Boolean(initial?.clientId));
  const project = projects.data?.find((item) => item.id === projectId) ?? null;
  const fieldId = useId();

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? undefined : onClose())}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t("upload.destination.title")}</DialogTitle>
          <DialogDescription>{t("upload.destination.description")}</DialogDescription>
        </DialogHeader>

        <form
          className="flex min-w-0 flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            // Un progetto scelto prima e poi archiviato non c'e' piu' nell'elenco.
            if (!project) return;
            if (wholeClient) {
              onConfirm({
                projectId,
                processId: null,
                clientId: project.clientId,
                label: t("upload.destination.wholeClient", { name: project.client }),
              });
              return;
            }
            const process = project.processItems.find((item) => item.id === processId);
            onConfirm({
              projectId,
              processId: processId || null,
              label: process ? `${project.name} · ${process.name}` : project.name,
            });
          }}
        >
          <div className="flex flex-col gap-1.5">
            <label htmlFor={`${fieldId}-project`} className="text-sm font-medium">
              {t("upload.destination.project")}
            </label>
            <select
              id={`${fieldId}-project`}
              value={projectId}
              required
              onChange={(event) => {
                setProjectId(event.target.value);
                // Un processo appartiene al suo progetto: cambiato il progetto, si riparte.
                setProcessId("");
                setWholeClient(false);
              }}
              className="h-9 w-full min-w-0 rounded-md border border-border bg-background px-3 text-sm"
              disabled={projects.isLoading}
            >
              <option value="" disabled>
                {projects.isLoading ? t("upload.destination.loading") : t("upload.destination.chooseProject")}
              </option>
              {(projects.data ?? []).map((item) => (
                <option key={item.id} value={item.id}>
                  {item.client ? `${item.name} · ${item.client}` : item.name}
                </option>
              ))}
            </select>
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor={`${fieldId}-process`} className="text-sm font-medium">
              {t("upload.destination.process")}
            </label>
            <select
              id={`${fieldId}-process`}
              aria-describedby={`${fieldId}-process-hint`}
              value={wholeClient ? CLIENT_SCOPE : processId}
              onChange={(event) => {
                setWholeClient(event.target.value === CLIENT_SCOPE);
                setProcessId(event.target.value === CLIENT_SCOPE ? "" : event.target.value);
              }}
              className="h-9 w-full min-w-0 rounded-md border border-border bg-background px-3 text-sm"
              disabled={!project}
            >
              {project?.clientId ? (
                <option value={CLIENT_SCOPE}>
                  {t("upload.destination.wholeClient", { name: project.client })}
                </option>
              ) : null}
              <option value="">{t("upload.destination.wholeProject")}</option>
              {(project?.processItems ?? []).map((process) => (
                <option key={process.id} value={process.id}>
                  {process.name}
                </option>
              ))}
            </select>
            <span id={`${fieldId}-process-hint`} className="text-xs text-muted-foreground">
              {wholeClient
                ? t("upload.destination.asClient")
                : processId
                  ? t("upload.destination.asEvidence")
                  : t("upload.destination.asContext")}
            </span>
          </div>

          {projects.isError ? (
            <p role="alert" className="text-sm text-destructive">
              {t("upload.destination.loadFailed")}
            </p>
          ) : null}

          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose}>
              {t("upload.destination.cancel")}
            </Button>
            <Button type="submit" disabled={!project}>
              {t("upload.destination.choose")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
