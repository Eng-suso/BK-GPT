import React from "react";
import { Flame } from "lucide-react";

import { PhasePlaceholder } from "./PhasePlaceholder";

export function HeatmapPage(): React.JSX.Element {
  return <PhasePlaceholder screenKey="heatmap" icon={Flame} />;
}
