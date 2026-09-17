import type { ProvenanceMarkStatus } from "@/contracts/workspace";
import type { BpmnModeler } from "./types";

/**
 * Il legame fra il disegno e il rapporto di provenance.
 *
 * Il backend scrive su ogni nodo tracciato l'attributo di estensione
 * `delir:provenance` e, nella documentazione, i `source_refs` con cui il
 * compilatore lega il nodo all'elemento del piano (`steps:apri_richiesta`). Qui
 * si leggono entrambi: il primo per segnare i nodi sul canvas, il secondo per
 * portare il consulente dal pannello delle evidenze al nodo giusto.
 *
 * Nessuna seconda mappa da tenere allineata: il disegno porta gia' tutto.
 */

const TRACEABILITY_MARKER = "DeliR traceability:";

/** I segni che il canvas mostra. `verified` e `paraphrased` non ne hanno: un
 * nodo che le fonti reggono non ha bisogno di attenzione, e segnarlo sarebbe
 * rumore sopra i nodi che invece ne hanno bisogno. */
export const MARKED_STATUSES: ReadonlySet<ProvenanceMarkStatus> = new Set([
  "unverified",
  "label_grounded",
  "confirmed",
]);

export const markerClass = (status: ProvenanceMarkStatus): string =>
  `delir-provenance-${status.replace("_", "-")}`;

const KNOWN: ReadonlySet<string> = new Set([
  "verified",
  "paraphrased",
  "label_grounded",
  "unverified",
  "confirmed",
]);

type BusinessObject = {
  $attrs?: Record<string, unknown>;
  documentation?: Array<{ text?: string }>;
};

type RegistryElement = {
  id: string;
  type?: string;
  businessObject?: BusinessObject;
};

/** Il riferimento di tracciabilita' scritto nella documentazione di un nodo. */
export function sourceRefsFromDocumentation(text: string | undefined): string[] {
  if (!text || !text.includes(TRACEABILITY_MARKER)) return [];
  const payload = text.split(TRACEABILITY_MARKER)[1]?.trim() ?? "";
  try {
    const parsed = JSON.parse(payload) as { source_refs?: unknown };
    return Array.isArray(parsed.source_refs)
      ? parsed.source_refs.filter((ref): ref is string => typeof ref === "string")
      : [];
  } catch {
    return [];
  }
}

/** L'esito di provenance di un nodo, qualunque prefisso abbia il namespace. */
export function provenanceOf(element: RegistryElement): ProvenanceMarkStatus | null {
  const attrs = element.businessObject?.$attrs ?? {};
  for (const [key, value] of Object.entries(attrs)) {
    if ((key === "provenance" || key.endsWith(":provenance") || key.endsWith("}provenance"))
      && typeof value === "string" && KNOWN.has(value)) {
      return value as ProvenanceMarkStatus;
    }
  }
  return null;
}

type Services = {
  registry: { getAll: () => RegistryElement[] };
  canvas: {
    addMarker: (id: string, marker: string) => void;
    removeMarker: (id: string, marker: string) => void;
  };
};

function services(modeler: BpmnModeler): Services {
  return {
    registry: modeler.get("elementRegistry") as Services["registry"],
    canvas: modeler.get("canvas") as Services["canvas"],
  };
}

/**
 * Segna i nodi secondo l'esito di provenance e indicizza i riferimenti.
 *
 * @returns Per ogni riferimento di tracciabilita', gli id dei nodi che lo
 *   rappresentano: un passaggio del piano puo' comparire in piu' punti (un ramo
 *   e il percorso principale).
 */
export function applyProvenanceMarkers(modeler: BpmnModeler): Map<string, string[]> {
  const { registry, canvas } = services(modeler);
  const index = new Map<string, string[]>();
  for (const element of registry.getAll()) {
    if (element.type === "label") continue;
    for (const status of MARKED_STATUSES) {
      canvas.removeMarker(element.id, markerClass(status));
    }
    const status = provenanceOf(element);
    if (status && MARKED_STATUSES.has(status)) {
      canvas.addMarker(element.id, markerClass(status));
    }
    for (const ref of sourceRefsFromDocumentation(element.businessObject?.documentation?.[0]?.text)) {
      index.set(ref, [...(index.get(ref) ?? []), element.id]);
    }
  }
  return index;
}

/**
 * Separa le note scritte dal consulente dal blocco di tracciabilita' del
 * compilatore, che vive nella stessa documentazione.
 *
 * L'ispettore mostrava il JSON di tracciabilita' come se fosse una nota, e
 * salvare una nota lo cancellava: il nodo smetteva di essere riconoscibile, il
 * pannello delle evidenze non lo ritrovava e i segni non si aggiornavano piu'.
 */
export function splitTraceability(text: string | undefined): {
  notes: string;
  traceability: string;
} {
  const value = text ?? "";
  const at = value.indexOf(TRACEABILITY_MARKER);
  if (at === -1) return { notes: value, traceability: "" };
  return {
    notes: value.slice(0, at).trimEnd(),
    traceability: value.slice(at),
  };
}

/** Le note nuove, con il blocco di tracciabilita' che il nodo aveva gia'. */
export function withTraceability(notes: string, traceability: string): string {
  if (!traceability) return notes;
  return notes.trim() ? `${notes.trimEnd()}

${traceability}` : traceability;
}
