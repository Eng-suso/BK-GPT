/**
 * Il processo raccontato a chi non ha mai visto un diagramma BPMN.
 *
 * Il responsabile del processo presso il cliente non legge gateway, corsie e
 * flussi: legge una lista di passi, nell'ordine in cui accadono, con chi li fa
 * e le decisioni scritte come domande. Questo modulo fa quella traduzione dal
 * disegno, senza aggiungere nulla che il disegno non dica.
 */

const BPMN = "http://www.omg.org/spec/BPMN/20100524/MODEL";
const ACTIVITIES = new Set([
  "task", "userTask", "manualTask", "serviceTask", "businessRuleTask", "scriptTask", "sendTask", "receiveTask",
  "subProcess", "callActivity", "transaction",
]);
const DECISIONS = new Set(["exclusiveGateway", "inclusiveGateway", "eventBasedGateway", "complexGateway"]);
const MIDDLE_EVENTS = new Set(["intermediateCatchEvent", "intermediateThrowEvent"]);

export type PlainStepKind = "activity" | "decision" | "parallel" | "wait";

/** Dove si va dopo un passo: un altro passo, oppure la fine del processo. */
export type PlainNext =
  | { kind: "step"; number: number; label: string }
  | { kind: "end"; name: string; label: string };

export type PlainStep = {
  id: string;
  number: number;
  kind: PlainStepKind;
  /** Il nome scritto nel disegno; vuoto se il disegno non ne ha uno. */
  name: string;
  /** La corsia del disegno, cioe' chi fa il passo; vuota se non indicata. */
  actor: string;
  next: PlainNext[];
};

export type PlainProcess = {
  /** Cosa fa partire il processo (gli eventi di inizio, con il loro nome). */
  starts: string[];
  steps: PlainStep[];
  /** Come puo' finire il processo. */
  ends: string[];
  /** Chi e' coinvolto e in quanti passi, nell'ordine in cui entra in scena. */
  actors: Array<{ name: string; steps: number }>;
};

type Node = { id: string; type: string; name: string };
type Flow = { target: string; label: string };

const EMPTY: PlainProcess = { starts: [], steps: [], ends: [], actors: [] };

/**
 * Traduce il disegno in passi. I nodi di unione (gateway con una sola uscita)
 * non diventano passi: per chi legge non succede niente, si va avanti e basta.
 * L'ordine e' quello in cui i passi si incontrano partendo dall'inizio; cio'
 * che dall'inizio non si raggiunge va in fondo, nell'ordine del disegno.
 */
export function readPlainProcess(xml: string | null | undefined): PlainProcess {
  if (!xml) return EMPTY;
  const document = new DOMParser().parseFromString(xml, "text/xml");
  if (document.querySelector("parsererror")) return EMPTY;
  const elements = Array.from(document.getElementsByTagNameNS(BPMN, "*"));

  const nodes = new Map<string, Node>();
  const outgoing = new Map<string, Flow[]>();
  const incoming = new Map<string, number>();
  const lane = new Map<string, string>();

  for (const element of elements) {
    const id = element.getAttribute("id") ?? "";
    const type = element.localName;
    if (type === "lane") {
      const name = clean(element.getAttribute("name"));
      for (const ref of Array.from(element.getElementsByTagNameNS(BPMN, "flowNodeRef"))) {
        if (ref.textContent && !lane.has(ref.textContent)) lane.set(ref.textContent, name);
      }
    } else if (type === "sequenceFlow") {
      const source = element.getAttribute("sourceRef") ?? "";
      const target = element.getAttribute("targetRef") ?? "";
      outgoing.set(source, [...(outgoing.get(source) ?? []), { target, label: clean(element.getAttribute("name")) }]);
      incoming.set(target, (incoming.get(target) ?? 0) + 1);
    } else if (id && (ACTIVITIES.has(type) || DECISIONS.has(type) || MIDDLE_EVENTS.has(type) || type === "parallelGateway" || type === "startEvent" || type === "endEvent")) {
      nodes.set(id, { id, type, name: clean(element.getAttribute("name")) });
    }
  }
  // Un passo dentro un sotto-processo appartiene al sotto-processo, non alla
  // lista principale: chi legge vede il sotto-processo come un passo solo.
  for (const element of elements) {
    if (element.localName !== "subProcess" && element.localName !== "transaction") continue;
    for (const child of Array.from(element.getElementsByTagNameNS(BPMN, "*"))) nodes.delete(child.getAttribute("id") ?? "");
  }

  const isGateway = (node: Node) => DECISIONS.has(node.type) || node.type === "parallelGateway";
  const isPassThrough = (node: Node) => isGateway(node) && (outgoing.get(node.id)?.length ?? 0) <= 1;
  const isStep = (node: Node) => node.type !== "startEvent" && node.type !== "endEvent" && !isPassThrough(node);

  /** Il prossimo nodo che conta per chi legge, saltando le unioni. */
  const resolve = (id: string, seen = new Set<string>()): Node | null => {
    const node = nodes.get(id);
    if (!node || seen.has(id)) return null;
    if (!isPassThrough(node)) return node;
    seen.add(id);
    const after = outgoing.get(id)?.[0];
    return after ? resolve(after.target, seen) : null;
  };

  const startNodes = [...nodes.values()].filter((node) => node.type === "startEvent");
  const roots = startNodes.length ? startNodes : [...nodes.values()].filter((node) => !incoming.get(node.id));
  const order: Node[] = [];
  const visited = new Set<string>();
  const queue = [...roots];
  while (queue.length) {
    const node = queue.shift()!;
    if (visited.has(node.id)) continue;
    visited.add(node.id);
    if (isStep(node)) order.push(node);
    for (const flow of outgoing.get(node.id) ?? []) {
      const target = nodes.get(flow.target);
      if (target && !visited.has(target.id)) queue.push(target);
    }
  }
  for (const node of nodes.values()) if (!visited.has(node.id) && isStep(node)) order.push(node);

  const number = new Map(order.map((node, index) => [node.id, index + 1]));
  const steps: PlainStep[] = order.map((node) => ({
    id: node.id,
    number: number.get(node.id)!,
    kind: DECISIONS.has(node.type) ? "decision" : node.type === "parallelGateway" ? "parallel" : MIDDLE_EVENTS.has(node.type) ? "wait" : "activity",
    name: node.name,
    actor: lane.get(node.id) ?? "",
    next: (outgoing.get(node.id) ?? []).flatMap((flow): PlainNext[] => {
      const target = resolve(flow.target);
      if (!target) return [];
      if (target.type === "endEvent") return [{ kind: "end", name: target.name, label: flow.label }];
      const n = number.get(target.id);
      return n ? [{ kind: "step", number: n, label: flow.label }] : [];
    }),
  }));

  const actors: PlainProcess["actors"] = [];
  for (const step of steps) {
    if (!step.actor || step.kind !== "activity") continue;
    const found = actors.find((item) => item.name === step.actor);
    if (found) found.steps += 1; else actors.push({ name: step.actor, steps: 1 });
  }

  return {
    starts: startNodes.map((node) => node.name),
    steps,
    ends: [...new Set([...nodes.values()].filter((node) => node.type === "endEvent").map((node) => node.name))],
    actors,
  };
}

/** I nomi nel disegno vanno spesso a capo a meta' parola: si ricompongono. */
function clean(value: string | null): string {
  return (value ?? "").replace(/\s+/g, " ").trim();
}
