import { describe, expect, it } from "vitest";
import { parsePaletteItem } from "./canvasPaletteModel";

describe("canvas palette boundary", () => {
  it("accepts catalog presets and rejects malformed or unsupported drops", () => {
    expect(parsePaletteItem('{"kind":"kpi","metric":"cost"}')).toEqual({ kind: "kpi", metric: "cost", note: undefined });
    expect(parsePaletteItem('{"kind":"text","note":true}')?.note).toBe(true);
    for (const raw of ["invalid", "null", '{"kind":"script"}', '{"kind":"kpi","metric":"external"}', '{"kind":"line","note":true}']) expect(parsePaletteItem(raw)).toBeNull();
  });
});
