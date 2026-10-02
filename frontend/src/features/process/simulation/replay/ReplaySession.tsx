import React from "react";

import { useReplayEngine } from "./useReplay";

import { ReplaySessionContext } from "./useReplaySession";

/** Owned by the workspace, so changing analysis routes keeps the same clock. */
export function ReplaySession({ runId, enabled, children }: {
  runId: number | null;
  enabled: boolean;
  children: React.ReactNode;
}): React.JSX.Element {
  const session = useReplayEngine(runId, enabled);
  return <ReplaySessionContext.Provider value={session}>{children}</ReplaySessionContext.Provider>;
}
