import { describe, expect, it } from "vitest";

import {
  applyProvenanceMarkers,
  markerClass,
  provenanceOf,
  sourceRefsFromDocumentation,
} from "./provenance";
import type { BpmnModeler } from "./types";

const DOC = 'Passaggio\n\nDeliR traceability:\n{"source_refs": ["steps:apri", "exceptions:ex"]}';

function fakeModeler(elements: Array<Record<string, unknown>>) {
  const markers = new Map<string, Set<string>>();
  const modeler = {
    get: (name: string) => {
      if (name === "elementRegistry") return { getAll: () => elements };
      if (name === "canvas") {
        return {
          addMarker: (id: string, marker: string) => {
            markers.set(id, new Set([...(markers.get(id) ?? []), marker]));
          },
          removeMarker: (id: string, marker: string) => {
            markers.get(id)?.delete(marker);
          },
        };
      }
      return undefined;
    },
  } as unknown as BpmnModeler;
  return { modeler, markers };
}

describe("provenance on the canvas", () => {
  it("reads the traceability references the compiler writes", () => {
    expect(sourceRefsFromDocumentation(DOC)).toEqual(["steps:apri", "exceptions:ex"]);
    expect(sourceRefsFromDocumentation("solo una nota")).toEqual([]);
    expect(sourceRefsFromDocumentation("DeliR traceability:\n{rotto")).toEqual([]);
  });

  it("reads the status whatever prefix the namespace got", () => {
    expect(provenanceOf({ id: "a", businessObject: { $attrs: { "delir:provenance": "unverified" } } })).toBe(
      "unverified",
    );
    expect(provenanceOf({ id: "a", businessObject: { $attrs: { "ns0:provenance": "confirmed" } } })).toBe(
      "confirmed",
    );
    expect(provenanceOf({ id: "a", businessObject: { $attrs: { "delir:provenance": "boh" } } })).toBeNull();
  });

  it("marks only what needs attention and indexes every traced node", () => {
    const { modeler, markers } = fakeModeler([
      { id: "t1", businessObject: { $attrs: { "delir:provenance": "verified" }, documentation: [{ text: DOC }] } },
      {
        id: "t2",
        businessObject: {
          $attrs: { "delir:provenance": "unverified" },
          documentation: [{ text: 'DeliR traceability:\n{"source_refs": ["steps:audit"]}' }],
        },
      },
      { id: "t2_label", type: "label", businessObject: { $attrs: { "delir:provenance": "unverified" } } },
    ]);

    const index = applyProvenanceMarkers(modeler);

    expect(markers.get("t1") ?? new Set()).toEqual(new Set());
    expect(markers.get("t2")).toEqual(new Set([markerClass("unverified")]));
    expect(markers.has("t2_label")).toBe(false);
    expect(index.get("steps:apri")).toEqual(["t1"]);
    expect(index.get("steps:audit")).toEqual(["t2"]);
  });

  it("drops a stale marker when the element is confirmed", () => {
    const element = {
      id: "t2",
      businessObject: { $attrs: { "delir:provenance": "unverified" } as Record<string, unknown> },
    };
    const { modeler, markers } = fakeModeler([element]);
    applyProvenanceMarkers(modeler);

    element.businessObject.$attrs["delir:provenance"] = "confirmed";
    applyProvenanceMarkers(modeler);

    expect(markers.get("t2")).toEqual(new Set([markerClass("confirmed")]));
  });
});
