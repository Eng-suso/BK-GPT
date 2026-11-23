import { describe, expect, it } from "vitest";
import { detectDateFormat, detectNumberFormat, suggestColumns } from "./eventLogSuggestions";

describe("event log import suggestions", () => {
  it("prefills recognizable business and XES columns without guessing unknown ones", () => {
    expect(suggestColumns(["Ordine", "Attività", "Fine", "Utente"]).caseId).toEqual(["Ordine"]);
    expect(suggestColumns(["case:concept:name", "concept:name", "time:timestamp", "lifecycle:transition"]).timeShape).toBe("transition");
    expect(suggestColumns(["Codice", "Descrizione", "Data"]).caseId).toEqual([]);
  });

  it("detects clear date formats and requests a choice for ambiguous dates", () => {
    expect(detectDateFormat(["23/11/2026 14:30", "24/11/2026 15:00"])).toEqual({ pattern: "%d/%m/%Y %H:%M", ambiguous: false });
    expect(detectDateFormat(["11/23/2026 14:30"])).toEqual({ pattern: "%m/%d/%Y %H:%M", ambiguous: false });
    expect(detectDateFormat(["03/04/2026 14:30"])).toEqual({ pattern: "", ambiguous: true });
    expect(detectDateFormat(["2026-11-23T14:30:00Z"])).toEqual({ pattern: "", ambiguous: false });
  });

  it("recognizes Italian and English numeric separators", () => {
    expect(detectNumberFormat(["1.200,50", "300,00"])).toEqual({ decimal: ",", thousands: "." });
    expect(detectNumberFormat(["1,200.50"])).toEqual({ decimal: ".", thousands: "," });
  });
});
