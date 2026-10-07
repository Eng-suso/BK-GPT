import { describe, expect, it } from "vitest";

import {
  addAttribute,
  draftFromMapping,
  draftIssues,
  emptyDraft,
  matchesFrom,
  missingTemplateColumns,
  toColumnMapping,
  usedColumns,
} from "./eventLogMapping";

describe("mapping draft", () => {
  it("lists what is missing before the backend would refuse it", () => {
    expect(draftIssues(emptyDraft())).toEqual(["caseId", "activity", "end"]);
    expect(draftIssues({ ...emptyDraft(), timeShape: "transition" })).toEqual(["caseId", "activity", "timestamp"]);
  });

  it("sends only the columns of the chosen time shape", () => {
    const draft = { ...emptyDraft(), caseId: ["Ordine"], activity: ["Attivita"], start: "Inizio", end: "Fine", timestamp: "Quando", lifecycle: "Stato" };

    const interval = toColumnMapping(draft);
    expect(interval).toMatchObject({ start: "Inizio", end: "Fine", timestamp: null, lifecycle: null });
    const transition = toColumnMapping({ ...draft, timeShape: "transition" });
    expect(transition).toMatchObject({ start: null, end: null, timestamp: "Quando", lifecycle: "Stato" });
    expect(draftIssues(draft)).toEqual([]);
  });

  it("round-trips a saved mapping and keeps formats", () => {
    const mapping = toColumnMapping({
      ...emptyDraft(),
      caseId: ["Ordine", "Riga"],
      activity: ["Attivita"],
      end: "Fine",
      resource: "Utente",
      caseAttributes: addAttribute([], "Importo", "number"),
      pattern: "%d/%m/%Y %H:%M",
      decimal: ",",
      thousands: ".",
    });

    expect(toColumnMapping(draftFromMapping(mapping))).toEqual(mapping);
    expect(mapping.timestamps).toEqual({ pattern: "%d/%m/%Y %H:%M", timezone: "Europe/Rome" });
    expect(mapping.numbers).toEqual({ decimal: ",", thousands: "." });
  });

  it("flags attributes without a name or with the same name", () => {
    const draft = { ...emptyDraft(), caseId: ["c"], activity: ["a"], end: "e" };
    expect(draftIssues({ ...draft, caseAttributes: [{ column: "x", name: " ", type: "text" }] })).toEqual(["attributeName"]);
    expect(
      draftIssues({
        ...draft,
        caseAttributes: addAttribute([], "Paese"),
        eventAttributes: addAttribute([], "Paese"),
      }),
    ).toEqual(["attributeNameDuplicate"]);
  });

  it("knows which columns a template needs from a new file", () => {
    const draft = { ...emptyDraft(), caseId: ["Ordine"], activity: ["Attivita"], end: "Fine", resource: "Utente" };
    const mapping = toColumnMapping(draft);

    expect([...usedColumns(draft)].sort()).toEqual(["Attivita", "Fine", "Ordine", "Utente"]);
    expect(missingTemplateColumns(mapping, ["Ordine", "Attivita", "Fine"])).toEqual(["Utente"]);
    expect(missingTemplateColumns(mapping, ["Ordine", "Attivita", "Fine", "Utente", "Altro"])).toEqual([]);
  });

  it("reads the current matches from a report", () => {
    expect(
      matchesFrom(
        [
          { activity: "Ricevi", element_id: "T1" },
          { activity: "Archivia", element_id: null },
        ],
        (row) => row.activity,
      ),
    ).toEqual({ Ricevi: "T1", Archivia: null });
    expect(matchesFrom([{ resource: "anna", model_resource_id: "lane-1" }], (row) => row.resource)).toEqual({ anna: "lane-1" });
  });
});
