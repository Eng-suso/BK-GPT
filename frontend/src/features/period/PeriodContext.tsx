import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import { PeriodContext, type PeriodValue } from "./periodContextValue";
import { DEFAULT_PERIOD, PERIOD_IDS, localDate, periodRange, today, type PeriodId } from "./periods";

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
  // Il giorno corrente fa parte dello stato: "questo mese" cambia a mezzanotte,
  // e una sessione lasciata aperta continuerebbe a filtrare sul mese scorso.
  const [day, setDay] = useState(() => today());

  useEffect(() => {
    const sync = () => setDay((current) => (current === today() ? current : today()));
    // Al ritorno sulla scheda e a mezzanotte: chi lascia il prodotto aperto di
    // notte non deve riaprirlo per vedere i numeri giusti.
    window.addEventListener("focus", sync);
    document.addEventListener("visibilitychange", sync);
    const timer = window.setInterval(sync, 60_000);
    return () => {
      window.removeEventListener("focus", sync);
      document.removeEventListener("visibilitychange", sync);
      window.clearInterval(timer);
    };
  }, []);

  const setPeriod = useCallback((next: PeriodId) => {
    setPeriodState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* storage non disponibile: la scelta vale per questa sessione */
    }
  }, []);

  const value = useMemo<PeriodValue>(
    // Il giorno entra nel calcolo, non solo nelle dipendenze: l'intervallo di
    // "questo mese" e' quello del giorno che il prodotto sta vivendo adesso.
    () => ({ period, range: periodRange(period, localDate(day)), setPeriod }),
    [period, day, setPeriod],
  );

  return <PeriodContext.Provider value={value}>{children}</PeriodContext.Provider>;
}
