import { useContext } from "react";

import { PeriodContext, type PeriodValue } from "./periodContextValue";
import { DEFAULT_PERIOD, periodRange } from "./periods";

/**
 * Il periodo scelto e il suo intervallo.
 *
 * Fuori dal provider vale "tutto": una schermata montata da sola (uno
 * Storybook, un test) deve mostrare il lavoro intero, non nasconderne meta'.
 */
export function usePeriod(): PeriodValue {
  const value = useContext(PeriodContext);
  if (value) return value;
  return {
    period: DEFAULT_PERIOD,
    range: periodRange(DEFAULT_PERIOD),
    setPeriod: () => {},
  };
}
