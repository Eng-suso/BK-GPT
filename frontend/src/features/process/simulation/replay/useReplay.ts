import React from "react";
import { useQuery } from "@tanstack/react-query";

import { HttpError } from "@/lib/http";
import { getSimulationReplay } from "../simulationApi";
import { ReplayEngine, type ReplayFrame, type ReplayStatus } from "./replayEngine";

type UseReplayEngine = {
  engine: ReplayEngine | null;
  isLoading: boolean;
  /** true when the run completed but produced no replay artifact (404). */
  noArtifact: boolean;
  error: string | null;
};

/**
 * Fetch a run's replay artifact and wrap it in a {@link ReplayEngine}. The
 * engine is recreated when the run changes and torn down on unmount.
 */
export function useReplayEngine(runId: number | null): UseReplayEngine {
  const query = useQuery({
    queryKey: ["workspace", "simulation-replay", runId],
    queryFn: () => getSimulationReplay(runId as number),
    enabled: runId != null,
    staleTime: Infinity,
    retry: (count, err) =>
      !(err instanceof HttpError && err.status === 404) && count < 2,
  });

  // The engine is derived purely from the fetched artifact (its constructor only
  // computes stats — no rAF / listeners until `.play()`), so build it in a memo
  // and dispose it in an effect keyed on the instance.
  const engine = React.useMemo(
    () => (query.data ? new ReplayEngine(query.data.replay) : null),
    [query.data],
  );
  React.useEffect(() => {
    if (!engine) return;
    return () => engine.destroy();
  }, [engine]);

  const noArtifact =
    query.isError && query.error instanceof HttpError && query.error.status === 404;

  return {
    engine,
    isLoading: runId != null && query.isLoading,
    noArtifact,
    error:
      query.isError && !noArtifact
        ? query.error instanceof Error
          ? query.error.message
          : "Replay non disponibile."
        : null,
  };
}

/** Bucket-rate frame: node states, counters, tokens, chart data. */
export function useReplayFrame(engine: ReplayEngine | null): ReplayFrame | null {
  return React.useSyncExternalStore(
    engine ? engine.subscribeFrame : noopSubscribe,
    engine ? engine.getFrame : nullSnapshot,
    engine ? engine.getFrame : nullSnapshot,
  );
}

/** Discrete transport state (no live `tNow`). */
export function useReplayStatus(engine: ReplayEngine | null): ReplayStatus | null {
  return React.useSyncExternalStore(
    engine ? engine.subscribeStatus : noopSubscribe,
    engine ? engine.getStatus : nullSnapshot,
    engine ? engine.getStatus : nullSnapshot,
  );
}

/**
 * ReplayClock-rate playhead in seconds, throttled to ~10fps for React consumers
 * (the clock readout). The token layer / scrubber thumb subscribe imperatively
 * via `engine.subscribeTick` instead and never round-trip through React.
 */
export function usePlayhead(engine: ReplayEngine | null): number {
  const [t, setT] = React.useState(0);

  React.useEffect(() => {
    if (!engine) return;
    // subscribeTick fires immediately, so a fresh engine resets `t` on its own.
    let last = 0;
    return engine.subscribeTick((tNow) => {
      const now = performance.now();
      if (now - last >= 100 || tNow === 0 || tNow >= engine.durationSec) {
        last = now;
        setT(tNow);
      }
    });
  }, [engine]);

  return t;
}

const noopSubscribe = () => () => {};
const nullSnapshot = () => null;
