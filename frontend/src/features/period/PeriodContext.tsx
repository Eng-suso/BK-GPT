import { useCallback, useMemo, useState, type ReactNode } from "react";

import { PeriodContext, type PeriodValue } from "./periodContextValue";
import { DEFAULT_PERIOD, PERIOD_IDS, periodRange, type PeriodId } from "./periods";

const STORAGE_KEY = "delir-period";

function storedPeriod(): PeriodId {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return PERIOD_IDS.includes(raw as PeriodId) ? (raw as PeriodId) : DEFAULT_PERIOD;
  } catch {
    // Finestra privata, storage bloccato: il periodo non e' un dato da
    // difendere, si riparte dal default.
    return DEFAULT_PERIOD;
  }
}

/**
 * Il periodo vive sopra le schermate perche' la sua tendina sta nella barra in
 * alto: sceglierlo sui progetti e ritrovarlo diverso sulla home sarebbe due
 * verita' nello stesso prodotto. Resta scelto al prossimo accesso, come la
 * lingua.
 */
export function PeriodProvider({ children }: { children: ReactNode }): React.JSX.Element {
  const [period, setPeriodState] = useState<PeriodId>(storedPeriod);

  const setPeriod = useCallback((next: PeriodId) => {
    setPeriodState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* storage non disponibile: la scelta vale per questa sessione */
    }
  }, []);

  const value = useMemo<PeriodValue>(
    () => ({ period, range: periodRange(period), setPeriod }),
    [period, setPeriod],
  );

  return <PeriodContext.Provider value={value}>{children}</PeriodContext.Provider>;
}
