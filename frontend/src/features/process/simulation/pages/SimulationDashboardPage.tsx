import React from "react";

import { ReplayGate } from "../replay/ReplayGate";
import { DashboardWorkspace } from "../dashboard/DashboardWorkspace";
import "../dashboard/dashboard.css";

export function SimulationDashboardPage(): React.JSX.Element {
  return <ReplayGate>{({ engine, run }) => <DashboardWorkspace engine={engine} run={run} />}</ReplayGate>;
}
