import { useCallback, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { SortingState } from "@tanstack/react-table";
import { Pencil, Plus } from "lucide-react";

import { PageHeader, WorkspaceListView } from "@/components/layout";
import { DataTable, DataTablePagination, ListToolbar } from "@/components/data";
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
import { useWorkspaceRefresh } from "@/lib/hooks/useWorkspaceRefresh";
import { buildClientColumns } from "../columns";
import { useClientsQuery } from "../api";
import { ClientFormDialog } from "../components/ClientFormDialog";
import { clientStatusTone, type Client } from "../types";

function matchClient(c: Client, q: string): boolean {
  return [c.name, c.sector, c.owner, c.contact].some((v) =>
    v.toLowerCase().includes(q),
  );
}

export function ClientsListPage(): React.JSX.Element {
  const { t } = useTranslation("clients");
  useWorkspaceRefresh();

  const { data: clients = [], isLoading, isError, refetch } = useClientsQuery();
  const [sorting, setSorting] = useState<SortingState>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // `null` = creazione, un cliente = modifica di quel record. `formSession`
  // cambia a ogni apertura e fa da `key` al dialog: la bozza riparte dai dati
  // correnti senza risincronizzare lo state in un effetto.
  const [editing, setEditing] = useState<Client | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [formSession, setFormSession] = useState(0);

  const filterDefs = useMemo<ListFilterDef<Client>[]>(
    () => [
      { id: "status", label: t("list.filter.status"), accessor: (c) => c.status },
      { id: "owner", label: t("list.filter.owner"), accessor: (c) => c.owner },
      { id: "sector", label: t("list.filter.sector"), accessor: (c) => c.sector },
    ],
    [t],
  );
  const filters = useListFilters(clients, filterDefs);

  const filtered = useMemo(
    () => clients.filter(filters.match),
    [clients, filters.match],
  );
  const list = usePagedList(filtered, matchClient);
  const selected =
    clients.find((c) => c.id === selectedId) ?? list.pageRows[0] ?? null;

  const columns = useMemo(() => buildClientColumns(t), [t]);
  const handleRowClick = useCallback((c: Client) => setSelectedId(c.id), []);

  const openCreate = useCallback(() => {
    setEditing(null);
    setFormSession((session) => session + 1);
    setFormOpen(true);
  }, []);

  const openEdit = useCallback((client: Client) => {
    setEditing(client);
    setFormSession((session) => session + 1);
    setFormOpen(true);
  }, []);

  return (
    <WorkspaceListView
      header={
        <PageHeader
          breadcrumbs={[
            { label: t("breadcrumb.clients"), to: ROUTES.clients.list },
            { label: t("breadcrumb.directory") },
          ]}
          title={t("list.title")}
          description={t("list.description")}
          count={clients.length || undefined}
          actions={
            <Button size="sm" onClick={openCreate}>
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
                subtitle={selected.sector}
              />
              <DetailPanelSection
                title={t("detail.summary")}
                action={
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 px-2 text-xs"
                    onClick={() => openEdit(selected)}
                  >
                    <Pencil /> {t("detail.actions.edit")}
                  </Button>
                }
              >
                <DetailPanelKeyValue
                  rows={[
                    {
                      label: t("list.columns.status"),
                      value: (
                        <StatusIndicator
                          tone={clientStatusTone(selected.status)}
                          label={selected.status}
                        />
                      ),
                    },
                    {
                      label: t("detail.activeProjects"),
                      value: String(selected.projects),
                    },
                    { label: t("detail.owner"), value: selected.owner },
                    {
                      label: t("detail.contact"),
                      value: selected.contact || "—",
                    },
                    {
                      label: t("detail.nextActivity"),
                      value: selected.nextActivity,
                    },
                  ]}
                />
              </DetailPanelSection>
              {selected.processes.length > 0 && (
                <DetailPanelSection title={t("detail.processes")}>
                  <PanelBulletList items={selected.processes.slice(0, 6)} />
                </DetailPanelSection>
              )}
              {selected.documents.length > 0 && (
                <DetailPanelSection title={t("detail.documents")}>
                  <ul className="flex flex-col text-xs text-muted-foreground">
                    {selected.documents.slice(0, 6).map((d) => (
                      <li key={d} className="py-1.5">
                        {d}
                      </li>
                    ))}
                  </ul>
                </DetailPanelSection>
              )}
            </>
          ) : (
            <div className="pt-4">
              <EmptyState variant="inline" title={t("detail.selectPrompt")} />
            </div>
          )}
        </DetailPanel>
      }
    >
      <ClientFormDialog
        key={formSession}
        open={formOpen}
        onOpenChange={setFormOpen}
        client={editing}
      />
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
          getRowId={(c) => c.id}
          isLoading={isLoading}
          sorting={sorting}
          onSortingChange={setSorting}
          selectedRowId={selected?.id ?? null}
          onRowClick={handleRowClick}
          emptyState={
            <EmptyState
              title={t("list.empty.title")}
              description={t("list.empty.description")}
              action={
                <Button size="sm" onClick={openCreate}>
                  <Plus /> {t("list.actions.new")}
                </Button>
              }
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

function PanelBulletList({ items }: { items: string[] }): React.JSX.Element {
  return (
    <ul className="flex flex-col text-xs text-foreground">
      {items.map((item) => (
        <li
          key={item}
          className="flex items-baseline gap-2 py-1.5 before:mt-[6px] before:size-[3px] before:flex-none before:rounded-full before:bg-muted-foreground before:content-['']"
        >
          {item}
        </li>
      ))}
    </ul>
  );
}
