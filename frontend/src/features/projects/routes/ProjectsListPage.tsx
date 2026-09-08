import { useCallback, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Download, Pencil, Plus } from "lucide-react";

import { PageHeader, WorkspaceListView } from "@/components/layout";
import {
  DataTable,
  DataTablePagination,
  ListSummary,
  ListToolbar,
  ProgressBar,
  type ListSummaryItem,
} from "@/components/data";
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
import { useListFilters, type ListFilterDef } from "@/lib/hooks/useListFilters";
import { useListQueryState } from "@/lib/hooks/useListQueryState";
import { useMediaQuery } from "@/lib/useMediaQuery";
import { toCsv, downloadCsv } from "@/lib/csv";
import {
  RecordLifecycleDialog,
  type LifecycleAction,
  type LifecycleTarget,
} from "@/features/archive/RecordLifecycleDialog";
import { buildProjectColumns } from "../columns";
import { useProjectsQuery } from "../api";
import { ProjectFormDialog } from "../components/ProjectFormDialog";
import { projectStatusTone, type Project } from "../types";

// L'ordine in cui il riepilogo mostra gli stati: prima quello che chiede
// attenzione, per ultimo quello che non ne chiede piu'.
const STATUS_ORDER: Project["status"][] = [
  "A rischio",
  "In corso",
  "In pausa",
  "Bozza",
  "Completato",
];

/**
 * Determines whether a project matches a search query across its searchable fields.
 *
 * @param p - The project to search
 * @param q - The lowercase search query
 * @returns `true` if any searchable project field contains the query, `false` otherwise.
 */
function matchProject(p: Project, q: string): boolean {
  return [p.name, p.client, p.phase, p.status, p.nextStep].some((v) =>
    v.toLowerCase().includes(q),
  );
}

function leadOf(p: Project, fallback: string): string {
  return p.processItems[0]?.owner ?? fallback;
}

function processCount(p: Project): number {
  return p.processes || p.processItems.length;
}

/**
 * Renders the project portfolio list with filtering, search, pagination, export, and project management actions.
 */
export function ProjectsListPage(): React.JSX.Element {
  const { t } = useTranslation("projects");
  const { t: tCommon } = useTranslation("common");
  const navigate = useNavigate();

  const { data: projects = [], isLoading, isError, refetch } = useProjectsQuery();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // `null` = creazione, un progetto = modifica di quel record. `formSession`
  // cambia a ogni apertura e fa da `key` al dialog: la bozza riparte dai dati
  // correnti senza risincronizzare lo state in un effetto.
  const [editing, setEditing] = useState<Project | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [formSession, setFormSession] = useState(0);
  // The detail panel only mounts at ≥1536px (the `panel` breakpoint); below
  // that a row click opens the full detail page instead of selecting into a
  // panel nobody can see.
  const hasPanel = useMediaQuery("(min-width: 1536px)");

  const qs = useListQueryState(10);

  const unassigned = t("list.owner.unassigned");
  const filterDefs = useMemo<ListFilterDef<Project>[]>(
    () => [
      { id: "client", label: t("list.filter.client"), accessor: (p) => p.client },
      { id: "status", label: t("list.filter.status"), accessor: (p) => p.status },
      { id: "phase", label: t("list.filter.phase"), accessor: (p) => p.phase },
      {
        id: "lead",
        label: t("list.filter.owner"),
        accessor: (p) => leadOf(p, unassigned),
      },
    ],
    [t, unassigned],
  );
  const filters = useListFilters(projects, filterDefs, {
    selected: qs.filters,
    onSelectedChange: qs.setFilters,
  });

  const filtered = useMemo(
    () => projects.filter(filters.match),
    [projects, filters.match],
  );
  const list = usePagedList(filtered, matchProject, {
    pageSize: qs.pageSize,
    search: qs.search,
    onSearchChange: qs.setSearch,
    page: qs.page,
    onPageChange: qs.setPage,
  });
  const selected = hasPanel
    ? (projects.find((p) => p.id === selectedId) ?? list.pageRows[0] ?? null)
    : null;

  const openDetail = useCallback(
    (id: string, tab?: string) =>
      navigate(
        tab
          ? `${ROUTES.projects.detail(id)}?tab=${tab}`
          : ROUTES.projects.detail(id),
      ),
    [navigate],
  );
  const handleRowClick = useCallback(
    (p: Project) => (hasPanel ? setSelectedId(p.id) : openDetail(p.id)),
    [hasPanel, openDetail],
  );

  const openCreate = useCallback(() => {
    setEditing(null);
    setFormSession((session) => session + 1);
    setFormOpen(true);
  }, []);

  const openEdit = useCallback((project: Project) => {
    setEditing(project);
    setFormSession((session) => session + 1);
    setFormOpen(true);
  }, []);

  // Chiudere ed eliminare un progetto passano dallo stesso dialog, che conta sui
  // dati cosa si porta dietro l'operazione.
  const [lifecycle, setLifecycle] = useState<{
    target: LifecycleTarget;
    action: LifecycleAction;
  } | null>(null);
  const openLifecycle = useCallback(
    (project: Project, action: LifecycleAction) =>
      setLifecycle({
        target: { kind: "project", id: project.id, name: project.name },
        action,
      }),
    [],
  );

  const columns = useMemo(
    () =>
      buildProjectColumns(t, {
        tCommon,
        onEdit: openEdit,
        onArchive: (project) => openLifecycle(project, "archive"),
        onDelete: (project) => openLifecycle(project, "delete"),
      }),
    [t, tCommon, openEdit, openLifecycle],
  );

  const { filters: activeFilters, setFilters } = qs;
  const summary = useMemo<ListSummaryItem[]>(() => {
    const counts = new Map<string, number>();
    for (const p of projects) counts.set(p.status, (counts.get(p.status) ?? 0) + 1);
    return STATUS_ORDER.filter((s) => counts.has(s)).map((status) => {
      const picked = activeFilters.status ?? [];
      const active = picked.length === 1 && picked[0] === status;
      return {
        label: status,
        count: counts.get(status) ?? 0,
        tone: projectStatusTone(status),
        active,
        onClick: () =>
          setFilters({ ...activeFilters, status: active ? [] : [status] }),
      };
    });
  }, [projects, activeFilters, setFilters]);

  const exportCsv = useCallback(() => {
    const rows = list.filtered.map((p) => [
      p.name,
      p.client,
      p.phase,
      leadOf(p, unassigned),
      p.status,
      processCount(p),
      p.progress,
    ]);
    const csv = toCsv(
      [
        t("list.columns.project"),
        t("list.columns.client"),
        t("list.columns.phase"),
        t("list.columns.lead"),
        t("list.columns.status"),
        t("list.columns.processes"),
        t("list.columns.progress"),
      ],
      rows,
    );
    downloadCsv(
      `${t("list.title").toLowerCase()}-${new Date().toISOString().slice(0, 10)}.csv`,
      csv,
    );
  }, [list.filtered, t, unassigned]);

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
          meta={summary.length > 0 ? <ListSummary items={summary} /> : undefined}
          actions={
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={exportCsv}
                disabled={list.filtered.length === 0}
              >
                <Download /> {t("list.actions.export")}
              </Button>
              <Button size="sm" onClick={openCreate}>
                <Plus /> {t("list.actions.new")}
              </Button>
            </>
          }
        />
      }
      toolbar={
        <ListToolbar
          search={list.search}
          onSearchChange={list.setSearch}
          searchPlaceholder={t("list.filter.placeholder")}
          filters={filters.menus}
          onClearFilters={filters.clear}
        />
      }
      detail={
        <DetailPanel className="hidden panel:flex">
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
                      label: t("list.columns.lead"),
                      value: leadOf(selected, unassigned),
                    },
                    {
                      label: t("list.columns.processes"),
                      value: String(processCount(selected)),
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
                  <ul className="flex flex-col text-xs text-foreground">
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
                  <Button size="sm" onClick={() => openDetail(selected.id)}>
                    {t("detail.panel.openProject")}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => openDetail(selected.id, "chat")}
                  >
                    {t("detail.actions.openChat")}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    className="col-span-2"
                    onClick={() => openEdit(selected)}
                  >
                    <Pencil /> {t("detail.actions.edit")}
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
      <ProjectFormDialog
        key={formSession}
        open={formOpen}
        onOpenChange={setFormOpen}
        project={editing}
      />
      <RecordLifecycleDialog
        target={lifecycle?.target ?? null}
        action={lifecycle?.action ?? "archive"}
        onOpenChange={(open) => {
          if (!open) setLifecycle(null);
        }}
        onDone={() => setSelectedId(null)}
      />
      {isError ? (
        <div className="flex flex-1 items-center justify-center ui-surface ui-surface-panel">
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
          sorting={qs.sorting}
          onSortingChange={qs.setSorting}
          selectedRowId={selected?.id ?? null}
          onRowClick={handleRowClick}
          emptyState={
            qs.search || filters.activeCount > 0 ? (
              <EmptyState
                title={t("list.noResults.title")}
                description={t("list.noResults.description")}
                action={
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      list.setSearch("");
                      filters.clear();
                    }}
                  >
                    {t("list.noResults.reset")}
                  </Button>
                }
              />
            ) : (
              <EmptyState
                title={t("list.empty.title")}
                description={t("list.empty.description")}
                action={
                  <Button size="sm" onClick={openCreate}>
                    <Plus /> {t("list.actions.new")}
                  </Button>
                }
              />
            )
          }
          footer={
            list.filtered.length > 0 ? (
              <DataTablePagination
                page={list.page}
                pageCount={list.pageCount}
                totalLabel={t("list.pagination.total", list.range)}
                onPageChange={list.setPage}
                pageSize={qs.pageSize}
                onPageSizeChange={qs.setPageSize}
              />
            ) : null
          }
        />
      )}
    </WorkspaceListView>
  );
}
