import React from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Loader2, XCircle } from "lucide-react";

import { Button } from "@/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/ui/dialog";
import { API_BASE } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  QUEUE_NAMES,
  fetchDegradation,
  fetchQueueHealth,
  statusKeys,
  type QueueStats,
} from "./api";

export interface ServiceStatusDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Il modello con cui sta lavorando la conversazione aperta, quando c'e'. */
  modelName?: string | null;
}

type Tone = "ok" | "warning" | "error";

/**
 * Una riga di stato: cosa si sta guardando, com'e' andata, e il dettaglio.
 */
function StatusRow({
  label,
  tone,
  value,
  detail,
}: {
  label: string;
  tone: Tone;
  value: string;
  detail?: React.ReactNode;
}): React.JSX.Element {
  const Icon = tone === "ok" ? CheckCircle2 : tone === "warning" ? AlertTriangle : XCircle;
  return (
    <div className="flex items-start gap-2.5 border-b border-border py-2.5 last:border-b-0">
      <Icon
        className={cn(
          "mt-0.5 size-4 shrink-0",
          tone === "ok" && "text-[var(--color-status-success)]",
          tone === "warning" && "text-[var(--color-status-warning)]",
          tone === "error" && "text-[var(--color-status-danger)]",
        )}
        aria-hidden="true"
      />
      <div className="min-w-0 flex-1">
        <p className="text-[13px] font-medium text-foreground">{label}</p>
        <p className="text-[12.5px] text-muted-foreground">{value}</p>
        {detail ? <div className="mt-1 text-[12px] text-muted-foreground">{detail}</div> : null}
      </div>
    </div>
  );
}

function queueStats(value: unknown): QueueStats | null {
  return value && typeof value === "object" ? (value as QueueStats) : null;
}

/**
 * Stato del servizio: dove parla il prodotto, se risponde, e che lavoro ha in coda.
 *
 * Sostituisce l'avviso che stampava l'indirizzo del backend e basta. La domanda
 * vera davanti a un cliente non e' quale URL sia configurato, ma se il sistema
 * sta rispondendo e se e' rimasto indietro con qualcosa: un guasto delle code si
 * vede come conoscenza che non arriva, e senza questo pannello si scambia per
 * una risposta sbagliata del modello.
 */
export const ServiceStatusDialog: React.FC<ServiceStatusDialogProps> = ({
  open,
  onOpenChange,
  modelName,
}) => {
  const { t } = useTranslation("common");

  const degradation = useQuery({
    queryKey: statusKeys.degradation(),
    queryFn: fetchDegradation,
    enabled: open,
    staleTime: 10_000,
  });
  const queues = useQuery({
    queryKey: statusKeys.queues(),
    queryFn: fetchQueueHealth,
    enabled: open,
    staleTime: 10_000,
  });

  const isChecking = degradation.isPending || queues.isPending;
  const unreachable = degradation.isError;
  const counters = Object.entries(degradation.data?.counters ?? {});

  const refresh = () => {
    void degradation.refetch();
    void queues.refetch();
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t("serviceStatus.title")}</DialogTitle>
          <DialogDescription>{t("serviceStatus.description")}</DialogDescription>
        </DialogHeader>

        <div className="flex flex-col">
          <StatusRow
            label={t("serviceStatus.endpoint")}
            tone={unreachable ? "error" : "ok"}
            value={API_BASE || t("serviceStatus.sameOrigin")}
          />

          {open && isChecking ? (
            <p
              className="flex items-center gap-2 py-3 text-[13px] text-muted-foreground"
              role="status"
            >
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
              {t("serviceStatus.checking")}
            </p>
          ) : unreachable ? (
            <StatusRow
              label={t("serviceStatus.connection")}
              tone="error"
              value={t("serviceStatus.unreachable")}
            />
          ) : (
            <>
              <StatusRow
                label={t("serviceStatus.connection")}
                tone={degradation.data?.status === "degraded" ? "warning" : "ok"}
                value={
                  degradation.data?.status === "degraded"
                    ? t("serviceStatus.degraded")
                    : t("serviceStatus.healthy")
                }
                detail={
                  counters.length > 0 ? (
                    <ul className="flex flex-col gap-0.5">
                      {counters.map(([key, count]) => (
                        <li key={key} className="tabular-nums">
                          {key}: {count}
                        </li>
                      ))}
                    </ul>
                  ) : undefined
                }
              />

              {queues.isError ? (
                <StatusRow
                  label={t("serviceStatus.queues")}
                  tone="warning"
                  value={t("serviceStatus.queuesUnknown")}
                />
              ) : queues.data?.status === "not_configured" ? (
                <StatusRow
                  label={t("serviceStatus.queues")}
                  tone="warning"
                  value={t("serviceStatus.queuesNotConfigured")}
                />
              ) : (
                QUEUE_NAMES.map((name) => {
                  const stats = queueStats(queues.data?.[name]);
                  if (!stats) return null;
                  if (stats.error) {
                    return (
                      <StatusRow
                        key={name}
                        label={name}
                        tone="warning"
                        value={t("serviceStatus.queuesUnknown")}
                      />
                    );
                  }
                  const stuck = stats.stuck ?? 0;
                  const dead = stats.dead_letter ?? 0;
                  return (
                    <StatusRow
                      key={name}
                      label={name}
                      // `stuck` puo' ancora passare da solo, `dead_letter` no:
                      // sono due allarmi diversi e non si sommano in uno.
                      tone={dead > 0 ? "error" : stuck > 0 ? "warning" : "ok"}
                      value={t("serviceStatus.queueCounts", {
                        pending: stats.pending ?? 0,
                        stuck,
                      })}
                      detail={
                        dead > 0 ? t("serviceStatus.deadLetter", { count: dead }) : undefined
                      }
                    />
                  );
                })
              )}
            </>
          )}

          {modelName ? (
            <StatusRow
              label={t("serviceStatus.model")}
              tone="ok"
              value={modelName}
            />
          ) : null}
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" size="sm" onClick={refresh}>
            {t("serviceStatus.refresh")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
