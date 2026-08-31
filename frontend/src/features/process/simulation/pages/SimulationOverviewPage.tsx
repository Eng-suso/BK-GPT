import React from "react";

import { SimulationWorkspace } from "../SimulationWorkspace";
import { useSimulationSection } from "../useSimulationSection";

/**
 * Panoramica — for now the full pre-existing simulation workspace (config +
 * model + results). Deeper screens (Replay, Cruscotto, Heatmap…) split out of
 * here in later phases.
 */
export function SimulationOverviewPage(): React.JSX.Element {
  const { process, bpmnXml } = useSimulationSection();
  return (
    <div className="h-full min-h-0">
      <SimulationWorkspace process={process} currentBpmnXml={bpmnXml} />
    </div>
  );
}
