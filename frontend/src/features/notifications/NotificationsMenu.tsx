import { useTranslation } from "react-i18next";
import { AlertTriangle, Bell, CheckCircle2, FileCheck2, Loader2, PlayCircle } from "lucide-react";

import { Button } from "@/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/ui/popover";
import { cn } from "@/lib/utils";
import { formatDate } from "@/lib/date";
import {
  FAILURE_KINDS,
  notificationHref,
  useMarkNotificationsRead,
  useNotificationsQuery,
  type Notification,
  type NotificationKind,
} from "./api";

const KIND_ICON: Record<NotificationKind, typeof Bell> = {
  plan_ready: FileCheck2,
  plan_failed: AlertTriangle,
  conformance_findings: AlertTriangle,
  simulation_done: PlayCircle,
  simulation_failed: AlertTriangle,
};

export interface NotificationsMenuProps {
  /** Apre l'avviso scelto. */
  onNavigate: (href: string) => void;
}

/**
 * La campanella: cosa e' successo mentre il consulente guardava altrove.
 *
 * Mostrava un `3` scritto a mano. Il lavoro vero succede in differita - un
 * piano si ricostruisce in coda, il confronto con le fonti gira dopo che il
 * disegno e' uscito, una simulazione finisce minuti dopo - e senza un posto
 * dove leggerlo ci si accorge di un rilievo solo riaprendo il processo giusto
 * per caso. Il numero sul badge e' quello dei non letti: quando e' zero, non
 * c'e' badge.
 */
export function NotificationsMenu({ onNavigate }: NotificationsMenuProps): React.JSX.Element {
  const { t, i18n } = useTranslation("common");
  const feed = useNotificationsQuery();
  const markRead = useMarkNotificationsRead();

  const items = feed.data?.items ?? [];
  const unread = feed.data?.unread ?? 0;
  const locale = i18n.language || "it";

  const open = (notification: Notification) => {
    if (!notification.read) markRead.mutate([notification.id]);
    onNavigate(notificationHref(notification));
  };

  const describe = (notification: Notification): string =>
    t(`notifications.kind.${notification.kind}`, {
      count: notification.count,
      version: notification.version ?? 0,
      process: notification.processName,
    });

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={
            unread > 0
              ? t("notifications.labelWithCount", { count: unread })
              : t("notifications.label")
          }
          // Visibile anche su schermo stretto: un piano fallito o un rilievo sono la
          // ragione per cui si riapre il prodotto, e su telefono la barra e' l'unico
          // posto dove possono comparire.
          className="relative grid size-[34px] shrink-0 place-items-center rounded-lg text-muted-foreground hover:bg-muted/60 focus-visible:outline-2 focus-visible:outline-ring"
        >
          <Bell className="size-[17px]" strokeWidth={1.7} />
          {unread > 0 ? (
            <span className="absolute right-0.5 top-0.5 grid min-w-[15px] place-items-center rounded-full border-2 border-card bg-[var(--color-status-danger)] px-[3px] text-[9px] font-bold text-white">
              {unread > 9 ? "9+" : unread}
            </span>
          ) : null}
        </button>
      </PopoverTrigger>

      <PopoverContent align="end" className="w-[min(28rem,calc(100vw-2rem))] p-0">
        <div className="flex items-center justify-between gap-2 border-b border-border px-3 py-2">
          <p className="text-[13px] font-semibold text-foreground">{t("notifications.title")}</p>
          {items.some((item) => !item.read) ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={markRead.isPending}
              onClick={() => markRead.mutate([])}
            >
              {t("notifications.markAllRead")}
            </Button>
          ) : null}
        </div>

        <div className="max-h-[60dvh] overflow-y-auto">
          {feed.isPending ? (
            <p
              className="flex items-center justify-center gap-2 px-3 py-6 text-[13px] text-muted-foreground"
              role="status"
            >
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
              {t("notifications.loading")}
            </p>
          ) : feed.isError ? (
            <div className="flex flex-col items-center gap-2 px-3 py-6 text-center">
              <p className="text-[13px] text-muted-foreground">{t("notifications.failed")}</p>
              <Button type="button" size="sm" variant="outline" onClick={() => void feed.refetch()}>
                {t("actions.retry")}
              </Button>
            </div>
          ) : items.length === 0 ? (
            <div className="flex flex-col items-center gap-1 px-3 py-8 text-center">
              <CheckCircle2
                className="size-5 text-[var(--color-status-success)]"
                aria-hidden="true"
              />
              <p className="text-[13px] font-medium text-foreground">
                {t("notifications.empty.title")}
              </p>
              <p className="text-[12.5px] text-muted-foreground">
                {t("notifications.empty.description")}
              </p>
            </div>
          ) : (
            <ul className="flex flex-col">
              {items.map((item) => {
                const Icon = KIND_ICON[item.kind];
                const isFailure = FAILURE_KINDS.includes(item.kind);
                return (
                  <li key={item.id} className="border-b border-border last:border-b-0">
                    <button
                      type="button"
                      onClick={() => open(item)}
                      className={cn(
                        "flex w-full items-start gap-2.5 px-3 py-2.5 text-left hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                        !item.read && "bg-accent/50",
                      )}
                    >
                      <Icon
                        className={cn(
                          "mt-0.5 size-4 shrink-0",
                          isFailure
                            ? "text-[var(--color-status-danger)]"
                            : item.kind === "conformance_findings"
                              ? "text-[var(--color-status-warning)]"
                              : "text-muted-foreground",
                        )}
                        aria-hidden="true"
                      />
                      <span className="min-w-0 flex-1">
                        <span className="flex items-baseline gap-2">
                          <span className="min-w-0 flex-1 text-[13px] font-medium text-foreground">
                            {describe(item)}
                          </span>
                          {!item.read ? (
                            // Un aria-label su uno span generico non viene letto:
                            // lo stato passa come testo nascosto, il pallino e' decorazione.
                            <>
                              <span
                                className="mt-1 size-1.5 shrink-0 rounded-full bg-[var(--color-status-info)]"
                                aria-hidden="true"
                              />
                              <span className="sr-only">{t("notifications.unread")}</span>
                            </>
                          ) : null}
                        </span>
                        <span className="block truncate text-[12px] text-muted-foreground">
                          {item.clientName} · {item.projectName} · {item.processName}
                        </span>
                        <span className="block text-[11px] tabular-nums text-muted-foreground">
                          {formatDate(item.occurredAt, locale)}
                          {isFailure && item.detail ? ` · ${item.detail}` : ""}
                        </span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
