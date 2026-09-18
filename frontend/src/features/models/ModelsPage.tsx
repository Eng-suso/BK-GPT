import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import type { ColumnDef } from "@tanstack/react-table";
import { Boxes } from "lucide-react";

import { ROUTES } from "@/app/routes";
import { PageHeader } from "@/components/layout";
import { EmptyState, ErrorState } from "@/components/feedback";
import { DataTable, ListSummary, ListToolbar } from "@/components/data";
import { StatusIndicator } from "@/components/status";
import type { StatusTone } from "@/components/status/tones";
import { Button } from "@/ui/button";
import { formatDate } from "@/lib/date";
import { useListFilters } from "@/lib/hooks/useListFilters";
import { modelHref, useModelsQuery, type ModelLibraryItem, type ModelStage } from "./api";

const STAGE_TONE: Record<ModelStage, StatusTone> = {
  toDraw: "neutral",
  noPlan: "pending",
  inReview: "pending",
  toFix: "warning",
  approved: "ok",
};

function matchesSearch(model: ModelLibraryItem, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  return [model.name, model.processName, model.projectName, model.clientName].some((value) =>
    value.toLowerCase().includes(needle),
  );
}

/**
 * Libreria modelli: ogni disegno BPMN del workspace in un posto solo.
 *
 * Era un segnaposto "in arrivo" mentre i modelli esistevano gia', uno per
 * processo, raggiungibili solo aprendo cliente, progetto e processo. Qui si
 * leggono insieme, con cio' che serve per decidere quale riaprire: se il
 * disegno c'e', a che punto e' la review, se il confronto con le fonti regge.
 */
export function ModelsPage(): React.JSX.Element {
  const { t, i18n } = useTranslation("common");
  const navigate = useNavigate();
  const { data = [], isLoading, isError, refetch } = useModelsQuery();
  const [search, setSearch] = useState("");

  const filters = useListFilters(data, [
    { id: "stage", label: t("models.columns.stage"), accessor: (m) => t(`models.stage.${m.stage}`) },
    { id: "client", label: t("models.columns.client"), accessor: (m) => m.clientName },
  ]);

  const rows = useMemo(
    () => data.filter((model) => filters.match(model) && matchesSearch(model, search)),
    [data, filters, search],
  );

  const summary = useMemo(() => {
    const count = (stage: ModelStage) => data.filter((m) => m.stage === stage).length;
    return [
      { label: t("models.stage.toDraw"), count: count("toDraw"), tone: STAGE_TONE.toDraw },
      {
        label: t("models.stage.inReview"),
        count: count("inReview") + count("noPlan"),
        tone: STAGE_TONE.inReview,
      },
      { label: t("models.stage.toFix"), count: count("toFix"), tone: STAGE_TONE.toFix },
      { label: t("models.stage.approved"), count: count("approved"), tone: STAGE_TONE.approved },
    ];
  }, [data, t]);

  const columns = useMemo<ColumnDef<ModelLibraryItem>[]>(
    () => [
      {
        id: "model",
        header: t("models.columns.model"),
        cell: ({ row }) => (
          <div className="min-w-0">
            <p className="truncate text-[13px] font-medium text-foreground">
              {row.original.processName}
            </p>
            <p className="truncate text-xs text-muted-foreground">
              {row.original.clientName} · {row.original.projectName}
            </p>
          </div>
        ),
      },
      {
        id: "stage",
        header: t("models.columns.stage"),
        cell: ({ row }) => (
          <StatusIndicator
            tone={STAGE_TONE[row.original.stage]}
            label={t(`models.stage.${row.original.stage}`)}
          />
        ),
      },
      {
        id: "diagram",
        header: t("models.columns.diagram"),
        cell: ({ row }) => (
          <span className="text-xs text-muted-foreground tabular-nums">
            {row.original.hasDiagram
              ? t("models.diagram.versions", { count: row.original.versionCount })
              : t("models.diagram.none")}
          </span>
        ),
      },
      {
        id: "review",
        header: t("models.columns.review"),
        cell: ({ row }) => {
          const model = row.original;
          if (model.reviewStatus == null) {
            return <span className="text-xs text-muted-foreground">{t("models.review.none")}</span>;
          }
          return (
            <span className="text-xs text-foreground tabular-nums">
              {model.reviewStatus === "approved"
                ? t("models.review.approved")
                : t("models.review.pending", { readiness: model.readiness ?? 0 })}
            </span>
          );
        },
      },
      {
        id: "conformance",
        header: t("models.columns.conformance"),
        cell: ({ row }) => {
          const model = row.original;
          if (model.conformancePending) {
            return <StatusIndicator tone="pending" label={t("models.conformance.pending")} />;
          }
          switch (model.conformanceVerdict) {
            case "conformant":
              return <StatusIndicator tone="ok" label={t("models.conformance.conformant")} />;
            case "conformant_with_divergences":
              return (
                <StatusIndicator
                  tone="warning"
                  label={t("models.conformance.divergences", { count: model.conformanceFindings })}
                />
              );
            case "not_conformant":
              return (
                <StatusIndicator
                  tone="danger"
                  label={t("models.conformance.notConformant", { count: model.conformanceFindings })}
                />
              );
            case "incomplete":
              return <StatusIndicator tone="warning" label={t("models.conformance.incomplete")} />;
            default:
              return <StatusIndicator tone="neutral" label={t("models.conformance.none")} />;
          }
        },
      },
      {
        id: "touched",
        header: t("models.columns.touched"),
        cell: ({ row }) => (
          <span className="text-xs text-muted-foreground tabular-nums">
            {row.original.touchedAt
              ? formatDate(row.original.touchedAt, i18n.language || "it")
              : "—"}
          </span>
        ),
      },
    ],
    [t, i18n.language],
  );

  return (
    <div className="flex h-full flex-col gap-4 overflow-auto px-4 py-6 sm:px-7">
      <PageHeader
        breadcrumbs={[{ label: t("nav.models") }]}
        title={t("nav.models")}
        description={t("models.description")}
        count={data.length || undefined}
        meta={data.length > 0 ? <ListSummary items={summary} /> : undefined}
      />

      <ListToolbar
        search={search}
        onSearchChange={setSearch}
        searchPlaceholder={t("models.searchPlaceholder")}
        filters={filters.menus}
        onClearFilters={filters.clear}
      />

      {isError ? (
        <div className="flex flex-1 items-center justify-center ui-surface ui-surface-panel">
          <ErrorState description={t("state.errorBody")} onRetry={() => void refetch()} />
        </div>
      ) : (
        <DataTable
          columns={columns}
          data={rows}
          getRowId={(model) => model.id}
          isLoading={isLoading}
          onRowClick={(model) => navigate(modelHref(model))}
          emptyState={
            search || filters.activeCount > 0 ? (
              <EmptyState
                title={t("models.noResults.title")}
                description={t("models.noResults.description")}
                action={
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setSearch("");
                      filters.clear();
                    }}
                  >
                    {t("models.noResults.reset")}
                  </Button>
                }
              />
            ) : (
              <EmptyState
                icon={Boxes}
                title={t("models.empty.title")}
                description={t("models.empty.description")}
                action={
                  <Button size="sm" onClick={() => navigate(ROUTES.projects.list)}>
                    {t("models.empty.action")}
                  </Button>
                }
              />
            )
          }
        />
      )}
    </div>
  );
}
