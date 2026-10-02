/**
 * Il contesto del periodo, in un file suo.
 *
 * Sta separato dal provider perche' il fast refresh ricarica solo i moduli che
 * esportano componenti: tenere qui il contesto evita che una modifica al
 * provider ricarichi mezza applicazione.
 */

import { createContext } from "react";

import type { PeriodId, PeriodRange } from "./periods";

export type PeriodValue = {
  period: PeriodId;
  range: PeriodRange;
  setPeriod: (period: PeriodId) => void;
};

export const PeriodContext = createContext<PeriodValue | null>(null);
