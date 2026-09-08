import type { ColumnDef } from "@tanstack/react-table";
import type { TFunction } from "i18next";
import { Archive, MoreHorizontal, Pencil, Trash2 } from "lucide-react";

import { ProgressBar } from "@/components/data";
import { StatusIndicator } from "@/components/status";
import { Button } from "@/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/ui/dropdown-menu";
import type { Project } from "./types";
import { projectStatusRank, projectStatusTone } from "./types";

export type ProjectRowActions = {
  onEdit: (project: Project) => void;
  onArchive: (project: Project) => void;
  onDelete: (project: Project) => void;
  /** Etichette dal namespace `common`, dove vive il vocabolario del ciclo di vita. */
  tCommon: TFunction;
};

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase() || "—";
}

export function buildProjectColumns(
  t: TFunction,
  actions?: ProjectRowActions,
): ColumnDef<Project>[] {
  const columns: ColumnDef<Project>[] = [
    {
      accessorKey: "name",
      header: t("list.columns.project"),
      cell: ({ row }) => (
        <span className="block max-w-[300px]">
          <span className="block truncate text-body-sm font-semibold tracking-[-0.012em] text-primary">
            {row.original.name}
          </span>
          <span className="block truncate text-xs text-muted-foreground">
            {row.original.nextStep}
          </span>
        </span>
      ),
    },
    {
      accessorKey: "client",
      header: t("list.columns.client"),
      cell: ({ getValue }) => (
        <span className="text-foreground">{getValue<string>()}</span>
      ),
    },
    {
      accessorKey: "phase",
      header: t("list.columns.phase"),
      cell: ({ getValue }) => (
        <span className="text-foreground">{getValue<string>()}</span>
      ),
    },
    {
      id: "lead",
      header: t("list.columns.lead"),
      enableSorting: false,
      cell: ({ row }) => {
        // Il referente dell'incarico, quando c'e'. Prima questa colonna mostrava
        // l'owner del primo processo registrato: un progetto senza processi non
        // aveva referente, e uno con tre ne mostrava uno a caso.
        const lead = row.original.lead || row.original.processItems[0]?.owner;
        return lead ? (
          <span className="inline-flex max-w-[160px] items-center gap-2">
            <span className="grid size-[23px] flex-none place-items-center rounded-full bg-muted text-2xs font-semibold text-muted-foreground ring-1 ring-black/5">
              {initials(lead)}
            </span>
            <span className="truncate text-foreground">{lead}</span>
          </span>
        ) : (
          <span className="text-muted-foreground">
            {t("list.owner.unassignedLead")}
          </span>
        );
      },
    },
    {
      accessorKey: "status",
      header: t("list.columns.status"),
      sortingFn: (a, b) =>
        projectStatusRank(a.original.status) -
        projectStatusRank(b.original.status),
      cell: ({ row }) => (
        <StatusIndicator
          tone={projectStatusTone(row.original.status)}
          label={row.original.status}
        />
      ),
    },
    {
      accessorKey: "processes",
      header: t("list.columns.processes"),
      cell: ({ row }) => (
        <span className="block text-right tabular-nums text-foreground">
          {row.original.processes || row.original.processItems.length}
        </span>
      ),
    },
    {
      accessorKey: "progress",
      header: t("list.columns.progress"),
      cell: ({ getValue }) => (
        <ProgressBar value={getValue<number>()} width={84} />
      ),
    },
  ];

  if (!actions) return columns;

  const { tCommon } = actions;
  columns.push({
    id: "actions",
    header: "",
    enableSorting: false,
    cell: ({ row }) => (
      <div className="flex justify-end">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label={`${tCommon("lifecycle.actions.more")}: ${row.original.name}`}
              onClick={(event) => event.stopPropagation()}
            >
              <MoreHorizontal />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onSelect={() => actions.onEdit(row.original)}>
              <Pencil />
              {tCommon("lifecycle.actions.edit")}
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => actions.onArchive(row.original)}>
              <Archive />
              {tCommon("lifecycle.actions.archive")}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              variant="destructive"
              onSelect={() => actions.onDelete(row.original)}
            >
              <Trash2 />
              {tCommon("lifecycle.actions.delete")}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    ),
  });

  return columns;
}
