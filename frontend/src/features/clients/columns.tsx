import type { ColumnDef } from "@tanstack/react-table";
import type { TFunction } from "i18next";
import { Archive, MoreHorizontal, Pencil, Trash2 } from "lucide-react";

import { StatusIndicator } from "@/components/status";
import { Button } from "@/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/ui/dropdown-menu";
import type { Client } from "./types";
import { clientStatusTone } from "./types";

export type ClientRowActions = {
  onEdit: (client: Client) => void;
  onArchive: (client: Client) => void;
  onDelete: (client: Client) => void;
  /** Etichette dal namespace `common`, dove vive il vocabolario del ciclo di vita. */
  tCommon: TFunction;
};

export function buildClientColumns(
  t: TFunction,
  actions?: ClientRowActions,
): ColumnDef<Client>[] {
  const columns: ColumnDef<Client>[] = [
    {
      accessorKey: "name",
      header: t("list.columns.client"),
      cell: ({ row }) => (
        <span className="block max-w-[280px]">
          <span className="block truncate text-[13.5px] font-semibold tracking-[-0.012em] text-primary">
            {row.original.name}
          </span>
          <span className="block truncate text-xs text-muted-foreground">
            {row.original.sector}
          </span>
        </span>
      ),
    },
    {
      accessorKey: "status",
      header: t("list.columns.status"),
      enableSorting: false,
      cell: ({ row }) => (
        <StatusIndicator
          tone={clientStatusTone(row.original.status)}
          label={row.original.status}
        />
      ),
    },
    {
      accessorKey: "projects",
      header: t("list.columns.projects"),
      cell: ({ getValue }) => (
        <span className="block text-right tabular-nums text-foreground">
          {getValue<number>()}
        </span>
      ),
    },
    {
      accessorKey: "nextActivity",
      header: t("list.columns.nextActivity"),
      cell: ({ getValue }) => (
        <span className="block max-w-[260px] truncate text-foreground">
          {getValue<string>()}
        </span>
      ),
    },
    {
      accessorKey: "owner",
      header: t("list.columns.owner"),
      cell: ({ getValue }) => (
        <span className="text-foreground">{getValue<string>()}</span>
      ),
    },
  ];

  if (!actions) return columns;

  // Le azioni stanno sulla riga, non solo nel pannello di dettaglio: quel
  // pannello sparisce sotto una certa larghezza, e con lui sparivano modifica,
  // chiusura ed eliminazione del cliente.
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
