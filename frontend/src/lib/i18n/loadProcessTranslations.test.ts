import type { BackendModule } from "i18next";
import { afterEach, describe, expect, it, vi } from "vitest";

import { i18n, loadProcessTranslations } from "@/lib/i18n";

describe("loadProcessTranslations", () => {
  afterEach(async () => {
    vi.restoreAllMocks();
    await i18n.changeLanguage("it");
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

  it("dopo un fallimento, la volta dopo ci riprova davvero", async () => {
    // i18next segna come fallito (-1) un namespace che il backend non ha
    // portato, e da li' in poi lo salta: senza rimedio, "Riprova" risolveva
    // subito e la pagina partiva senza parole. Qui il backend e' quello vero,
    // e fallisce solo la prima lettura.
    const backend = i18n.services.backendConnector.backend as BackendModule;
    const read = vi.spyOn(backend, "read").mockImplementationOnce((_language, _namespace, callback) => {
      callback(new Error("rete giu'"), false);
    });
    await i18n.changeLanguage("it");
    i18n.removeResourceBundle("it", "process");

    await expect(loadProcessTranslations()).rejects.toThrow("process translations not loaded");
    expect(i18n.hasResourceBundle("it", "process")).toBe(false);

    await expect(loadProcessTranslations()).resolves.toBeUndefined();
    expect(read).toHaveBeenCalledTimes(2);
    expect(i18n.hasResourceBundle("it", "process")).toBe(true);
  });

  it("non si fida di un fallimento lasciato da qualcun altro", async () => {
    // Un cambio di lingua su una schermata di processo carica `process` senza
    // passare da qui: se fallisce, lo stato fallito resta, e la chiamata dopo
    // risolveva senza leggere. Si risolve solo con il file davvero in memoria.
    const backend = i18n.services.backendConnector.backend as BackendModule;
    const read = vi.spyOn(backend, "read").mockImplementationOnce((_language, _namespace, callback) => {
      callback(new Error("rete giu'"), false);
    });
    await i18n.changeLanguage("it");
    i18n.removeResourceBundle("it", "process");
    await i18n.loadNamespaces("process");
    expect(i18n.hasResourceBundle("it", "process")).toBe(false);

    await expect(loadProcessTranslations()).resolves.toBeUndefined();
    expect(read).toHaveBeenCalledTimes(2);
    expect(i18n.hasResourceBundle("it", "process")).toBe(true);
  });
});
