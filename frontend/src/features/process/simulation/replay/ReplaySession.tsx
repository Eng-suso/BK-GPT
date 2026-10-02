import React from "react";

import { useReplayEngine, type UseReplayEngine } from "./useReplay";

const ReplaySessionContext = React.createContext<UseReplayEngine | null>(null);

/** Owned by the workspace, so changing analysis routes keeps the same clock. */
export function ReplaySession({ runId, enabled, children }: {
  runId: number | null;
  enabled: boolean;
  children: React.ReactNode;
}): React.JSX.Element {
  const session = useReplayEngine(runId, enabled);
  return <ReplaySessionContext.Provider value={session}>{children}</ReplaySessionContext.Provider>;
}

export function useReplaySession(): UseReplayEngine {
  const session = React.useContext(ReplaySessionContext);
  if (!session) throw new Error("ReplaySession requires the simulation workspace");
  return session;
}
