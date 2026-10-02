import React from "react";
import type { UseReplayEngine } from "./useReplay";

export const ReplaySessionContext = React.createContext<UseReplayEngine | null>(null);

export function useReplaySession(): UseReplayEngine {
  const session = React.useContext(ReplaySessionContext);
  if (!session) throw new Error("ReplaySession requires the simulation workspace");
  return session;
}
