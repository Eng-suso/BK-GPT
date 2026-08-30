import type { ColumnDef } from "@tanstack/react-table";
import type { TFunction } from "i18next";

import { StatusIndicator } from "@/components/status";
import type { Client } from "./types";
import { clientStatusTone } from "./types";

export function buildClientColumns(t: TFunction): ColumnDef<Client>[] {
  return [
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
}
