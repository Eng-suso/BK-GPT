import { useState } from "react";
import type { Meta, StoryObj } from "@storybook/react";
import type { ColumnDef, SortingState } from "@tanstack/react-table";

import { EmptyState } from "@/components/feedback/EmptyState";
import { StatusIndicator, type StatusTone } from "@/components/status/StatusIndicator";
import { DataTable } from "./DataTable";
import { DataTablePagination } from "./DataTablePagination";
import { ProgressBar } from "./ProgressBar";

type Project = {
  id: string;
  name: string;
  subtitle: string;
  client: string;
  phase: string;
  owner: string;
  status: { tone: StatusTone; label: string };
  processes: number;
  progress: number;
};

const ROWS: Project[] = [
  { id: "1", name: "Trasformazione Supply Chain", subtitle: "Ridisegno end-to-end", client: "Acme S.p.A.", phase: "Implementazione", owner: "Sara Bellini", status: { tone: "ok", label: "In corso" }, processes: 28, progress: 62 },
  { id: "2", name: "Ottimizzazione Order-to-Cash", subtitle: "Miglioramento ciclo O2C", client: "Beta Industria", phase: "Analisi", owner: "Fabio Moretti", status: { tone: "ok", label: "In corso" }, processes: 21, progress: 38 },
  { id: "3", name: "Ridefinizione Processo Acquisti", subtitle: "Efficienza e compliance", client: "Delta S.r.l.", phase: "Design", owner: "Sara Bellini", status: { tone: "warning", label: "In ritardo" }, processes: 14, progress: 72 },
  { id: "4", name: "PMO e Governance", subtitle: "Setup PMO e KPI", client: "Epsilon S.p.A.", phase: "Pianificazione", owner: "Fabio Moretti", status: { tone: "neutral", label: "Bozza" }, processes: 9, progress: 18 },
];

const columns: ColumnDef<Project>[] = [
  {
    accessorKey: "name",
    header: "Progetto",
    cell: ({ row }) => (
      <span>
        <span className="block font-semibold tracking-[-0.012em] text-primary">
          {row.original.name}
        </span>
        <span className="text-xs text-muted-foreground">
          {row.original.subtitle}
        </span>
      </span>
    ),
  },
  { accessorKey: "client", header: "Cliente" },
  { accessorKey: "phase", header: "Fase" },
  { accessorKey: "owner", header: "Owner" },
  {
    accessorKey: "status",
    header: "Stato",
    enableSorting: false,
    cell: ({ row }) => (
      <StatusIndicator
        tone={row.original.status.tone}
        label={row.original.status.label}
      />
    ),
  },
  {
    accessorKey: "processes",
    header: "Proc.",
    cell: ({ getValue }) => (
      <span className="tabular-nums text-foreground">{getValue<number>()}</span>
    ),
  },
  {
    accessorKey: "progress",
    header: "Avanzamento",
    cell: ({ getValue }) => <ProgressBar value={getValue<number>()} />,
  },
];

function DataTableDemo(): React.JSX.Element {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [selected, setSelected] = useState<string | null>("1");
  return (
    <div className="flex h-screen flex-col p-6">
      <DataTable
        columns={columns}
        data={ROWS}
        getRowId={(r) => r.id}
        sorting={sorting}
        onSortingChange={setSorting}
        selectedRowId={selected}
        onRowClick={(r) => setSelected(r.id)}
        footer={
          <DataTablePagination
            page={1}
            pageCount={3}
            totalLabel="Vista 1–4 di 24 progetti"
            onPageChange={() => undefined}
          />
        }
      />
    </div>
  );
}

const meta: Meta = {
  title: "Components/DataTable",
  parameters: { layout: "fullscreen" },
};
export default meta;
type Story = StoryObj;

export const Default: Story = { render: () => <DataTableDemo /> };

export const Loading: Story = {
  render: () => (
    <div className="flex h-screen flex-col p-6">
      <DataTable
        columns={columns}
        data={[]}
        getRowId={(r: Project) => r.id}
        isLoading
      />
    </div>
  ),
};

export const Empty: Story = {
  render: () => (
    <div className="flex h-screen flex-col p-6">
      <DataTable
        columns={columns}
        data={[]}
        getRowId={(r: Project) => r.id}
        emptyState={
          <EmptyState
            title="Nessun progetto"
            description="Crea il primo progetto dalla chat agente."
          />
        }
      />
    </div>
  ),
};
