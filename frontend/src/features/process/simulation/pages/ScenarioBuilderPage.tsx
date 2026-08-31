import React from "react";
import { SlidersHorizontal } from "lucide-react";

import { PhasePlaceholder } from "./PhasePlaceholder";

export function ScenarioBuilderPage(): React.JSX.Element {
  return <PhasePlaceholder screenKey="scenario" icon={SlidersHorizontal} />;
}
