import type { ColumnDef } from "@tanstack/react-table";
import type { TFunction } from "i18next";
import { Star } from "lucide-react";

import { ProgressBar } from "@/components/data";
import { StatusIndicator } from "@/components/status";
import type { Project } from "./types";
import { projectStatusTone } from "./types";

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase() || "—";
}

export function buildProjectColumns(t: TFunction): ColumnDef<Project>[] {
  return [
    {
      id: "favorite",
      header: "",
      enableSorting: false,
      size: 36,
      cell: () => (
        <Star className="size-[15px] text-muted-foreground/70" strokeWidth={1.6} />
      ),
    },
    {
      accessorKey: "name",
      header: t("list.columns.project"),
      cell: ({ row }) => (
        <span className="block max-w-[300px]">
          <span className="block truncate text-[13.5px] font-semibold tracking-[-0.012em] text-primary">
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
      id: "owner",
      header: t("list.columns.owner"),
      enableSorting: false,
      cell: ({ row }) => {
        const owner = row.original.processItems[0]?.owner;
        return owner ? (
          <span className="inline-flex max-w-[160px] items-center gap-2">
            <span className="grid size-[23px] flex-none place-items-center rounded-full bg-muted text-[9.5px] font-semibold text-muted-foreground ring-1 ring-black/5">
              {initials(owner)}
            </span>
            <span className="truncate text-foreground">{owner}</span>
          </span>
        ) : (
          <span className="text-muted-foreground">
            {t("list.owner.unassigned")}
          </span>
        );
      },
    },
    {
      accessorKey: "status",
      header: t("list.columns.status"),
      enableSorting: false,
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
      cell: ({ getValue }) => <ProgressBar value={getValue<number>()} width={84} />,
    },
  ];
}
