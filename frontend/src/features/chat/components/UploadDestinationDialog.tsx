import React, { useState } from "react";
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
 * evidenza di quel processo; messo nel progetto, contesto.
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
  const project = projects.data?.find((item) => item.id === projectId) ?? null;

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? undefined : onClose())}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t("upload.destination.title")}</DialogTitle>
          <DialogDescription>{t("upload.destination.description")}</DialogDescription>
        </DialogHeader>

        <form
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            if (!projectId) return;
            const process = project?.processItems.find((item) => item.id === processId);
            onConfirm({
              projectId,
              processId: processId || null,
              label: process ? `${project?.name} · ${process.name}` : project?.name,
            });
          }}
        >
          <label className="flex flex-col gap-1.5 text-sm font-medium">
            {t("upload.destination.project")}
            <select
              value={projectId}
              required
              onChange={(event) => {
                setProjectId(event.target.value);
                // Un processo appartiene al suo progetto: cambiato il progetto, si riparte.
                setProcessId("");
              }}
              className="h-9 rounded-md border border-border bg-background px-3 text-sm"
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
          </label>

          <label className="flex flex-col gap-1.5 text-sm font-medium">
            {t("upload.destination.process")}
            <select
              value={processId}
              onChange={(event) => setProcessId(event.target.value)}
              className="h-9 rounded-md border border-border bg-background px-3 text-sm"
              disabled={!project}
            >
              <option value="">{t("upload.destination.wholeProject")}</option>
              {(project?.processItems ?? []).map((process) => (
                <option key={process.id} value={process.id}>
                  {process.name}
                </option>
              ))}
            </select>
            <span className="text-xs font-normal text-muted-foreground">
              {processId ? t("upload.destination.asEvidence") : t("upload.destination.asContext")}
            </span>
          </label>

          {projects.isError ? (
            <p role="alert" className="text-sm text-destructive">
              {t("upload.destination.loadFailed")}
            </p>
          ) : null}

          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose}>
              {t("upload.destination.cancel")}
            </Button>
            <Button type="submit" disabled={!projectId}>
              {t("upload.destination.choose")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
