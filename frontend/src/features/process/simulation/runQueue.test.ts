import { describe, expect, it } from "vitest";

import { i18n } from "@/lib/i18n";

import { runWaitHint, runWaitTitle } from "./runQueue";

const t = i18n.getFixedT("it", "process");

describe("what a waiting run says (P0.3)", () => {
  it("gives the queue position and why it waits", () => {
    expect(runWaitTitle("queued", 3, t)).toBe("In coda: posizione 3");
    expect(runWaitHint("queued", t)).toBe("Parte appena il motore ha un posto libero. Puoi lasciare la pagina: la simulazione resta in coda.");
  });

  it("says running once the engine has taken it, or without queue data", () => {
    expect(runWaitTitle("running", null, t)).toBe("Simulazione in corso…");
    expect(runWaitTitle(undefined, undefined, t)).toBe("Simulazione in corso…");
    expect(runWaitHint("running", t)).toBeUndefined();
  });
});
