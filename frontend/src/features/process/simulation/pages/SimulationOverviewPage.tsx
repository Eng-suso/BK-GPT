import React from "react";

import { SimulationWorkspace } from "../SimulationWorkspace";

/**
 * Panoramica — the active run's KPI snapshot plus the scenario / model / results
 * on one scrolling page. (Everything is inside `SimulationWorkspace`, which reads
 * the section context.)
 */
export function SimulationOverviewPage(): React.JSX.Element {
  return <SimulationWorkspace />;
}
