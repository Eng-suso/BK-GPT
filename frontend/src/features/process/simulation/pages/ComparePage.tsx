import React from "react";
import { Columns2 } from "lucide-react";

import { PhasePlaceholder } from "./PhasePlaceholder";

export function ComparePage(): React.JSX.Element {
  return <PhasePlaceholder screenKey="compare" icon={Columns2} />;
}
