import type { Meta, StoryObj } from "@storybook/react";
import { MoreHorizontal } from "lucide-react";

import { ProgressBar } from "@/components/data/ProgressBar";
import { PriorityTag } from "@/components/status/PriorityTag";
import { StatusIndicator } from "@/components/status/StatusIndicator";
import {
  DetailPanel,
  DetailPanelHeader,
  DetailPanelKeyValue,
  DetailPanelSection,
} from "./DetailPanel";

const meta: Meta = {
  title: "Components/DetailPanel",
  parameters: { layout: "fullscreen" },
};
export default meta;
type Story = StoryObj;

export const ProjectSummary: Story = {
  render: () => (
    <div className="flex h-screen justify-end bg-background">
      <DetailPanel className="w-[352px]">
        <DetailPanelHeader
          title="Trasformazione Supply Chain"
          subtitle="Acme S.p.A."
          onClose={() => undefined}
        />
        <DetailPanelSection title="Riepilogo progetto">
          <DetailPanelKeyValue
            rows={[
              { label: "Fase corrente", value: "Implementazione" },
              {
                label: "Stato",
                value: <StatusIndicator tone="ok" label="In corso" />,
              },
              { label: "Owner", value: "Sara Bellini" },
              { label: "Processi in scope", value: "28" },
              {
                label: "Avanzamento",
                value: <ProgressBar value={62} width={74} />,
              },
            ]}
          />
        </DetailPanelSection>
        <DetailPanelSection
          title="Punti aperti"
          action={
            <button type="button" className="text-muted-foreground">
              <MoreHorizontal className="size-3.5" />
            </button>
          }
        >
          <ul className="flex flex-col text-[12.5px]">
            <li className="flex items-center gap-2 border-b border-border/60 py-2">
              Requisiti integrazione WMS
              <PriorityTag priority="alta" className="ml-auto" />
            </li>
            <li className="flex items-center gap-2 py-2">
              Allineamento su KPI di servizio
              <PriorityTag priority="media" className="ml-auto" />
            </li>
          </ul>
        </DetailPanelSection>
      </DetailPanel>
    </div>
  ),
};
