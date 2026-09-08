import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Archive, RotateCcw, Trash2 } from "lucide-react";

import { PageHeader } from "@/components/layout";
import { EmptyState, ErrorState } from "@/components/feedback";
import { Button } from "@/ui/button";
import { Skeleton } from "@/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/ui/tabs";
import { formatDate } from "@/lib/date";
import { useArchiveQuery } from "./api";
import {
  RecordLifecycleDialog,
  type LifecycleAction,
  type LifecycleTarget,
} from "./RecordLifecycleDialog";

type ArchivedRow = LifecycleTarget & {
  meta: string;
  archivedAt: string | null;
  archiveReason: string | null;
};

/**
 * Archivio: quello che è stato chiuso, non quello che è sparito.
 *
 * Prima questa pagina era un segnaposto "in arrivo", e il workspace non aveva
 * modo di chiudere un incarico: un cliente concluso restava nell'elenco del
 * lavoro corrente finché qualcuno non lo cancellava, perdendo con lui progetti,
 * processi, fonti e decisioni.
 */
export function ArchivePage(): React.JSX.Element {
  const { t } = useTranslation("common");
  const archiveQuery = useArchiveQuery();
  const [target, setTarget] = useState<LifecycleTarget | null>(null);
  const [action, setAction] = useState<LifecycleAction>("restore");

  const groups = useMemo(() => {
    const data = archiveQuery.data;
    return {
      clients: (data?.clients ?? []).map<ArchivedRow>((client) => ({
        kind: "client",
        id: client.id,
        name: client.name,
        meta: client.sector,
        archivedAt: client.archivedAt,
        archiveReason: client.archiveReason,
      })),
      projects: (data?.projects ?? []).map<ArchivedRow>((project) => ({
        kind: "project",
        id: project.id,
        name: project.name,
        meta: project.client,
        archivedAt: project.archivedAt,
        archiveReason: project.archiveReason,
      })),
      processes: (data?.processes ?? []).map<ArchivedRow>((process) => ({
        kind: "process",
        id: process.id,
        name: process.name,
        meta: `${process.stage} · ${process.owner}`,
        archivedAt: process.archivedAt,
        archiveReason: process.archiveReason,
      })),
    };
  }, [archiveQuery.data]);

  const total =
    groups.clients.length + groups.projects.length + groups.processes.length;

  const open = (row: ArchivedRow, next: LifecycleAction) => {
    setTarget({ kind: row.kind, id: row.id, name: row.name });
    setAction(next);
  };

  return (
    <div className="flex h-full flex-col gap-4 overflow-auto px-7 py-6">
      <PageHeader
        breadcrumbs={[{ label: t("nav.archive") }]}
        title={t("nav.archive")}
        description={t("archive.description")}
        count={total || undefined}
      />

      {archiveQuery.isLoading ? (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-9 w-72" />
          <Skeleton className="h-40 w-full" />
        </div>
      ) : archiveQuery.isError ? (
        <div className="flex flex-1 items-center justify-center ui-surface ui-surface-panel">
          <ErrorState
            description={t("state.errorBody")}
            onRetry={() => void archiveQuery.refetch()}
          />
        </div>
      ) : total === 0 ? (
        <div className="flex flex-1 items-center justify-center ui-surface ui-surface-panel">
          <EmptyState
            icon={Archive}
            title={t("nav.archive")}
            description={t("archive.empty")}
          />
        </div>
      ) : (
        <Tabs defaultValue="clients" className="flex min-w-0 flex-col gap-4">
          <TabsList variant="line" className="min-w-max">
            <TabsTrigger value="clients">
              {t("archive.tabs.clients")} ({groups.clients.length})
            </TabsTrigger>
            <TabsTrigger value="projects">
              {t("archive.tabs.projects")} ({groups.projects.length})
            </TabsTrigger>
            <TabsTrigger value="processes">
              {t("archive.tabs.processes")} ({groups.processes.length})
            </TabsTrigger>
          </TabsList>

          {(["clients", "projects", "processes"] as const).map((group) => (
            <TabsContent key={group} value={group}>
              <ArchivedList rows={groups[group]} onAction={open} />
            </TabsContent>
          ))}
        </Tabs>
      )}

      <RecordLifecycleDialog
        target={target}
        action={action}
        onOpenChange={(next) => {
          if (!next) setTarget(null);
        }}
      />
    </div>
  );
}

function ArchivedList({
  rows,
  onAction,
}: {
  rows: ArchivedRow[];
  onAction: (row: ArchivedRow, action: LifecycleAction) => void;
}): React.JSX.Element {
  const { t, i18n } = useTranslation("common");

  if (rows.length === 0) {
    return <EmptyState variant="inline" title={t("archive.empty")} />;
  }

  return (
    <ul className="flex flex-col ui-surface ui-surface-panel">
      {rows.map((row) => (
        <li
          key={`${row.kind}-${row.id}`}
          className="flex flex-wrap items-center gap-3 border-b border-border/60 px-4 py-3 last:border-b-0"
        >
          <div className="flex min-w-0 flex-1 flex-col">
            <span className="truncate text-body-sm font-medium text-foreground">
              {row.name}
            </span>
            <span className="truncate text-micro text-muted-foreground">
              {row.meta}
              {row.archivedAt
                ? ` · ${t("archive.closedOn")} ${formatDate(row.archivedAt, i18n.language)}`
                : ""}
            </span>
            <span className="truncate text-micro text-muted-foreground">
              {t("archive.reason")}:{" "}
              {row.archiveReason || t("archive.noReason")}
            </span>
          </div>
          <div className="flex flex-none items-center gap-1.5">
            <Button
              variant="outline"
              size="sm"
              onClick={() => onAction(row, "restore")}
            >
              <RotateCcw /> {t("lifecycle.actions.restore")}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="text-[var(--color-status-danger)] hover:bg-destructive/10"
              onClick={() => onAction(row, "delete")}
            >
              <Trash2 /> {t("lifecycle.actions.delete")}
            </Button>
          </div>
        </li>
      ))}
    </ul>
  );
}

