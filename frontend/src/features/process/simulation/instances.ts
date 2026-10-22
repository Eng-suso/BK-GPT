/** SIM-11h: le istanze per caso che il motore sa eseguire, come ``Activity.instances`` dell'IR. */
export const MAX_INSTANCES = 50;

/** Un numero di istanze impostato che non è un intero da 1 a 50; assente va bene (una istanza). */
export function instancesIssue(instances: number | undefined): "range" | null {
  if (instances === undefined) return null;
  return Number.isInteger(instances) && instances >= 1 && instances <= MAX_INSTANCES ? null : "range";
}
