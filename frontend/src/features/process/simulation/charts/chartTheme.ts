/** Shared theming for the Cruscotto charts. DeliR is light-only, so one set of
 *  values; each metric keeps a fixed colour across the whole dashboard. */

export const SIM_SERIES = {
  throughput: "var(--sim-chart-throughput)",
  wip: "var(--sim-chart-wip)",
  queue: "var(--sim-chart-queue)",
  cost: "var(--sim-chart-cost)",
  cycle: "var(--sim-chart-cycle)",
} as const;

/** left inset (Y axis width) + right inset — playhead alignment relies on these */
export const CHART_INSET = { left: 52, right: 10, top: 6, bottom: 20 } as const;

export const axisProps = {
  stroke: "var(--sim-chart-axis)",
  tick: { fill: "var(--sim-chart-axis)", fontSize: 11 },
  tickLine: false,
  axisLine: false,
} as const;

export const gridProps = {
  stroke: "var(--sim-chart-grid)",
  strokeDasharray: "2 4",
  vertical: false,
} as const;
