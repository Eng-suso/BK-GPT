import { afterEach, describe, expect, it, vi } from "vitest";

import { i18n, loadProcessTranslations } from "@/lib/i18n";

describe("loadProcessTranslations", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("dice quando process.json non arriva, invece di risolvere comunque", async () => {
    // i18next risolve la sua promessa anche quando il file non arriva: l'errore
    // va solo alla callback. Chi aspettava apriva la schermata con le chiavi.
    vi.spyOn(i18n, "loadNamespaces").mockImplementation((_ns, callback) => {
      callback?.(new Error("rete giu'"), i18n.t);
      return Promise.resolve();
    });

    await expect(loadProcessTranslations()).rejects.toThrow("process translations not loaded");
  });

  it("risolve quando le traduzioni ci sono", async () => {
    await expect(loadProcessTranslations()).resolves.toBeUndefined();
  });
});
