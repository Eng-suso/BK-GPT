import React from "react";
import { Sparkles } from "lucide-react";

import { PhasePlaceholder } from "./PhasePlaceholder";

export function InsightsPage(): React.JSX.Element {
  return <PhasePlaceholder screenKey="insights" icon={Sparkles} />;
}
