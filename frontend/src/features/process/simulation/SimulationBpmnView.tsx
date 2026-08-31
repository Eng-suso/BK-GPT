import React from "react";
import { useTranslation } from "react-i18next";
import { PanelLeftOpen } from "lucide-react";

import { Button } from "@/ui/button";

import { SimulationCanvas, type NodeDecoration } from "./canvas/SimulationCanvas";

/** One diagram node's aggregate (post-run) annotation. */
export type SimulationNodeOverlay = {
  elementId: string;
  waitLabel: string;
  /** 0 (cool) – 4 (hot) heat bucket by average waiting time. */
  heat: 0 | 1 | 2 | 3 | 4;
  /** Show a text badge (bottleneck + worst few); the rest get a tint only. */
  showBadge: boolean;
  isBottleneck: boolean;
};

const HEAT_MARKERS = ["sim-heat-0", "sim-heat-1", "sim-heat-2", "sim-heat-3", "sim-heat-4"];

type SimulationBpmnViewProps = {
  bpmnXml: string | null | undefined;
  overlays?: SimulationNodeOverlay[];
  selectedElementId?: string | null;
  onSelectElement?: (elementId: string | null) => void;
  /** When set, a leading "open scenario" button appears in the toolbar. */
  onExpandRail?: () => void;
  className?: string;
};

/**
 * Aggregate (post-run) view of the model: heat tint + bottleneck badges from a
 * finished run's statistics. The live Prosimos-log replay lives on the dedicated
 * Replay screen (`ReplayPage`), not here.
 */
export function SimulationBpmnView({
  bpmnXml,
  overlays = [],
  selectedElementId,
  onSelectElement,
  onExpandRail,
  className,
}: SimulationBpmnViewProps): React.JSX.Element {
  const { t } = useTranslation("process");

  const decorations = React.useMemo<NodeDecoration[]>(
    () =>
      overlays.map((item) => ({
        elementId: item.elementId,
        markers: [
          HEAT_MARKERS[item.heat],
          ...(item.isBottleneck ? ["sim-node-bottleneck"] : []),
        ],
        badge: item.showBadge ? item.waitLabel : undefined,
        badgeTone: item.isBottleneck ? "warning" : "neutral",
      })),
    [overlays],
  );

  return (
    <SimulationCanvas
      className={className}
      bpmnXml={bpmnXml}
      decorations={decorations}
      selectedElementId={selectedElementId}
      onSelectElement={onSelectElement}
      toolbarStart={
        onExpandRail ? (
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="mr-0.5 size-8 p-0 text-muted-foreground"
            onClick={onExpandRail}
            aria-label={t("simulation.config.expand")}
          >
            <PanelLeftOpen className="size-4" />
          </Button>
        ) : undefined
      }
    />
  );
}
