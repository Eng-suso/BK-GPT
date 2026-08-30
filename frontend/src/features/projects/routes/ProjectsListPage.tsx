import { useCallback, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { SortingState } from "@tanstack/react-table";
import { Plus } from "lucide-react";

import { PageHeader, WorkspaceListView } from "@/components/layout";
import { DataTable, DataTablePagination, ListToolbar, ProgressBar } from "@/components/data";
import { EmptyState, ErrorState } from "@/components/feedback";
import { StatusIndicator } from "@/components/status";
import {
  DetailPanel,
  DetailPanelHeader,
  DetailPanelKeyValue,
  DetailPanelSection,
} from "@/components/panel";
import { Button } from "@/ui/button";
import { ROUTES } from "@/app/routes";
import { usePagedList } from "@/lib/hooks/usePagedList";
import { useWorkspaceRefresh } from "@/lib/hooks/useWorkspaceRefresh";
import { buildProjectColumns } from "../columns";
import { useProjectsQuery } from "../api";
import { projectStatusTone, type Project } from "../types";

const FILTER_IDS = ["client", "status", "phase", "owner"] as const;

function matchProject(p: Project, q: string): boolean {
  return [p.name, p.client, p.phase, p.status, p.nextStep].some((v) =>
    v.toLowerCase().includes(q),
  );
}

export function ProjectsListPage(): React.JSX.Element {
  const { t } = useTranslation("projects");
  const navigate = useNavigate();
  useWorkspaceRefresh();

  const { data: projects = [], isLoading, isError, refetch } = useProjectsQuery();
  const [sorting, setSorting] = useState<SortingState>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const list = usePagedList(projects, matchProject);
  const selected =
    projects.find((p) => p.id === selectedId) ?? list.pageRows[0] ?? null;

  const columns = useMemo(() => buildProjectColumns(t), [t]);
  const handleRowClick = useCallback((p: Project) => setSelectedId(p.id), []);
  const openDetail = useCallback(
    (id: string) => navigate(ROUTES.projects.detail(id)),
    [navigate],
  );

  return (
    <WorkspaceListView
      header={
        <PageHeader
          breadcrumbs={[
            { label: t("breadcrumb.projects"), to: ROUTES.projects.list },
            { label: t("breadcrumb.portfolio") },
          ]}
          title={t("list.title")}
          description={t("list.description")}
          count={projects.length || undefined}
          actions={
            <Button size="sm">
              <Plus /> {t("list.actions.new")}
            </Button>
          }
        />
      }
      toolbar={
        <ListToolbar
          search={list.search}
          onSearchChange={list.setSearch}
          searchPlaceholder={t("list.filter.placeholder")}
          filters={FILTER_IDS.map((id) => ({ id, label: t(`list.filter.${id}`) }))}
        />
      }
      detail={
        <DetailPanel className="hidden xl:flex">
          {selected ? (
            <>
              <DetailPanelHeader
                title={selected.name}
                subtitle={selected.client}
              />
              <DetailPanelSection title={t("detail.panel.summary")}>
                <DetailPanelKeyValue
                  rows={[
                    { label: t("list.columns.phase"), value: selected.phase },
                    {
                      label: t("list.columns.status"),
                      value: (
                        <StatusIndicator
                          tone={projectStatusTone(selected.status)}
                          label={selected.status}
                        />
                      ),
                    },
                    {
                      label: t("list.columns.owner"),
                      value:
                        selected.processItems[0]?.owner ??
                        t("list.owner.unassigned"),
                    },
                    {
                      label: t("list.columns.processes"),
                      value: String(
                        selected.processes || selected.processItems.length,
                      ),
                    },
                    {
                      label: t("list.columns.progress"),
                      value: <ProgressBar value={selected.progress} width={74} />,
                    },
                  ]}
                />
              </DetailPanelSection>

              {selected.openIssues.length > 0 && (
                <DetailPanelSection title={t("detail.panel.openIssues")}>
                  <ul className="flex flex-col text-[12.5px] text-foreground">
                    {selected.openIssues.slice(0, 4).map((issue) => (
                      <li
                        key={issue}
                        className="flex items-baseline gap-2 py-1.5 before:mt-[6px] before:size-[3px] before:flex-none before:rounded-full before:bg-muted-foreground before:content-['']"
                      >
                        {issue}
                      </li>
                    ))}
                  </ul>
                </DetailPanelSection>
              )}

              <DetailPanelSection title={t("detail.panel.actions")}>
                <div className="grid grid-cols-2 gap-2 pb-5">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => openDetail(selected.id)}
                  >
                    {t("detail.panel.openRoadmap")}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => openDetail(selected.id)}
                  >
                    {t("detail.panel.openProcesses")}
                  </Button>
                </div>
              </DetailPanelSection>
            </>
          ) : (
            <div className="pt-4">
              <EmptyState
                variant="inline"
                title={t("detail.panel.selectPrompt")}
              />
            </div>
          )}
        </DetailPanel>
      }
    >
      {isError ? (
        <div className="flex flex-1 items-center justify-center rounded-xl border border-border bg-card">
          <ErrorState
            description={t("state.loadError")}
            onRetry={() => void refetch()}
          />
        </div>
      ) : (
        <DataTable
          columns={columns}
          data={list.pageRows}
          getRowId={(p) => p.id}
          isLoading={isLoading}
          sorting={sorting}
          onSortingChange={setSorting}
          selectedRowId={selected?.id ?? null}
          onRowClick={handleRowClick}
          emptyState={
            <EmptyState
              title={t("list.empty.title")}
              description={t("list.empty.description")}
            />
          }
          footer={
            list.filtered.length > 0 ? (
              <DataTablePagination
                page={list.page}
                pageCount={list.pageCount}
                totalLabel={t("list.pagination.total", list.range)}
                onPageChange={list.setPage}
              />
            ) : null
          }
        />
      )}
    </WorkspaceListView>
  );
}
