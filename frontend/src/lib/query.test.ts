import { describe, expect, it } from "vitest";

import { HttpError } from "./http";
import { shouldRetry } from "./query";

describe("shouldRetry", () => {
  it("un 429 generico si ritenta una volta", () => {
    expect(shouldRetry(0, new HttpError(429, "troppe richieste"))).toBe(true);
    expect(shouldRetry(1, new HttpError(429, "troppe richieste"))).toBe(false);
  });

  it("il limite d'uso della prova non si ritenta: si ripristina con la sessione", () => {
    const limit = new HttpError(429, "limite", { error: { code: "usage_limit_reached" } });
    expect(shouldRetry(0, limit)).toBe(false);
  });

  it("gli altri 4xx non si ritentano", () => {
    expect(shouldRetry(0, new HttpError(404, "non trovato"))).toBe(false);
  });
});
