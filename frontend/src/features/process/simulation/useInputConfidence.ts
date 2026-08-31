import React from "react";
import { useQuery } from "@tanstack/react-query";

import { fetchScenarioProvenance } from "./simulationApi";
import type { ScenarioProvenance, ScenarioTemplate } from "./simulationTypes";
import type { ScenarioDraft } from "./simulationScenario";
import { buildInputConfidence, type InputConfidence } from "./simulationProvenance";

type UseInputConfidence = {
  provenance: ScenarioProvenance | null;
  confidence: InputConfidence;
  isLoading: boolean;
};

/**
 * Fetches the structural provenance for a model once and rolls it up against the
 * live scenario draft. Cheap to call from several screens — the query is cached
 * on the model id.
 */
export function useInputConfidence(
  bpmnModelId: string,
  draft: ScenarioDraft,
  template: ScenarioTemplate | null,
  enabled = true,
): UseInputConfidence {
  const query = useQuery({
    queryKey: ["workspace", "simulation-provenance", bpmnModelId],
    queryFn: () => fetchScenarioProvenance(bpmnModelId, null),
    enabled: enabled && Boolean(bpmnModelId),
    staleTime: 60_000,
  });

  const provenance = query.data ?? null;
  const confidence = React.useMemo(
    () => buildInputConfidence(draft, template, provenance),
    [draft, template, provenance],
  );

  return { provenance, confidence, isLoading: query.isLoading };
}
