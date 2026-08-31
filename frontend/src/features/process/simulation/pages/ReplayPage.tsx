import React from "react";
import { Play } from "lucide-react";

import { PhasePlaceholder } from "./PhasePlaceholder";

export function ReplayPage(): React.JSX.Element {
  return <PhasePlaceholder screenKey="replay" icon={Play} />;
}
