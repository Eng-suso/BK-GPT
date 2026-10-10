/**
 * SIM-14: uno scenario del workspace come patch sulla bozza AS-IS.
 *
 * Stessa logica di `backend/simulation/scenario_patch.py` (i casi di
 * `tests/fixtures/simulation/scenario_patch_cases.json` valgono per entrambe):
 * un passo e' una chiave o `{ id }` per l'elemento di una lista con quell'id,
 * cosi' la patch di una risorsa resta valida se l'AS-IS ne aggiunge un'altra.
 * Un percorso che nell'AS-IS non esiste piu' e' un conflitto, non un oggetto a meta'.
 */

export type ScenarioPathStep = string | { id: string };
export type ScenarioPatchOp =
  | { op: "set"; path: ScenarioPathStep[]; value: unknown }
  | { op: "remove"; path: ScenarioPathStep[] }
  | { op: "order"; path: ScenarioPathStep[]; ids: string[] };

type Json = unknown;
type JsonObject = Record<string, Json>;

const isObject = (value: Json): value is JsonObject =>
  typeof value === "object" && value !== null && !Array.isArray(value);
const stepId = (step: ScenarioPathStep): string | null => (typeof step === "object" ? step.id : null);
const findById = (items: Json[], id: string) => items.findIndex((item) => isObject(item) && item.id === id);
const clone = <T>(value: T): T => (value === undefined ? value : JSON.parse(JSON.stringify(value)));

function child(container: Json, step: ScenarioPathStep): Json {
  const id = stepId(step);
  if (id !== null) {
    if (!Array.isArray(container)) return undefined;
    const index = findById(container, id);
    return index >= 0 ? container[index] : undefined;
  }
  return isObject(container) ? container[step as string] : undefined;
}

function applyOne(draft: JsonObject, op: ScenarioPatchOp): boolean {
  let parent: Json = draft;
  for (const step of op.path.slice(0, -1)) {
    parent = child(parent, step);
    if (!(isObject(parent) || Array.isArray(parent))) return false;
  }
  const last = op.path[op.path.length - 1];
  if (op.op === "order") {
    const target = child(parent, last);
    if (!Array.isArray(target)) return false;
    const wanted = [...new Set(op.ids)];
    const listed = wanted.map((id) => findById(target, id)).filter((i) => i >= 0).map((i) => target[i]);
    const rest = target.filter((item) => !(isObject(item) && wanted.includes(String(item.id))));
    target.splice(0, target.length, ...listed, ...rest);
    return true;
  }
  const id = stepId(last);
  if (id !== null) {
    if (!Array.isArray(parent)) return false;
    const index = findById(parent, id);
    if (op.op === "remove") {
      if (index >= 0) parent.splice(index, 1);
      return true;
    }
    const value = clone(op.value);
    if (!(isObject(value) && value.id === id)) return false;
    if (index >= 0) parent[index] = value;
    else parent.push(value);
    return true;
  }
  if (!isObject(parent) || typeof last !== "string") return false;
  if (op.op === "remove") delete parent[last];
  else parent[last] = clone(op.value);
  return true;
}

/** La bozza dello scenario e gli indici delle operazioni che non si applicano piu'. */
export function applyScenarioPatch<T extends object>(baseline: T, ops: ScenarioPatchOp[]): { draft: T; conflicts: number[] } {
  const draft = clone(baseline) as unknown as JsonObject;
  const conflicts = ops.flatMap((op, index) => (applyOne(draft, op) ? [] : [index]));
  return { draft: draft as unknown as T, conflicts };
}

function equal(a: Json, b: Json): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

/** Una lista di oggetti con id unici: si confronta elemento per elemento. */
function idList(value: Json): value is JsonObject[] {
  if (!Array.isArray(value) || value.length === 0) return false;
  const ids = value.map((item) => (isObject(item) && typeof item.id === "string" ? item.id : null));
  return ids.every((id) => id !== null) && new Set(ids).size === ids.length;
}

function diffInto(base: Json, target: Json, path: ScenarioPathStep[], ops: ScenarioPatchOp[]): void {
  if (equal(base, target)) return;
  if (isObject(base) && isObject(target)) {
    for (const key of Object.keys(target)) {
      if (!(key in base)) ops.push({ op: "set", path: [...path, key], value: clone(target[key]) });
      else diffInto(base[key], target[key], [...path, key], ops);
    }
    for (const key of Object.keys(base)) if (!(key in target)) ops.push({ op: "remove", path: [...path, key] });
    return;
  }
  // Due liste di elementi con id (anche una delle due vuota): per id, poi l'ordine.
  if (Array.isArray(base) && Array.isArray(target) && (idList(base) || base.length === 0) && (idList(target) || target.length === 0) && (base.length || target.length)) {
    const baseIds = (base as JsonObject[]).map((item) => String(item.id));
    const targetIds = (target as JsonObject[]).map((item) => String(item.id));
    for (const item of target as JsonObject[]) {
      const id = String(item.id);
      const index = baseIds.indexOf(id);
      if (index < 0) ops.push({ op: "set", path: [...path, { id }], value: clone(item) });
      else diffInto(base[index], item, [...path, { id }], ops);
    }
    for (const id of baseIds) if (!targetIds.includes(id)) ops.push({ op: "remove", path: [...path, { id }] });
    // Dopo set e remove l'ordine e': quelli dell'AS-IS rimasti, poi i nuovi in fondo.
    const natural = [...baseIds.filter((id) => targetIds.includes(id)), ...targetIds.filter((id) => !baseIds.includes(id))];
    if (!equal(natural, targetIds)) ops.push({ op: "order", path, ids: targetIds });
    return;
  }
  ops.push({ op: "set", path, value: clone(target) });
}

/**
 * Le differenze di `target` dall'AS-IS, come patch. Le chiavi `undefined` non
 * contano (come nel JSON salvato): `applyScenarioPatch(base, diff)` da' `target`.
 */
export function diffScenario(base: object, target: object): ScenarioPatchOp[] {
  const ops: ScenarioPatchOp[] = [];
  diffInto(clone(base), clone(target), [], ops);
  return ops;
}
