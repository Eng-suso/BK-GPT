import React from "react";
import { Activity } from "lucide-react";

import { PhasePlaceholder } from "./PhasePlaceholder";

export function SimulationDashboardPage(): React.JSX.Element {
  return <PhasePlaceholder screenKey="dashboard" icon={Activity} />;
}
