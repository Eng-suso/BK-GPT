import i18next, { type BackendModule } from "i18next";
import { initReactI18next } from "react-i18next";

import enChat from "@/locales/en/chat.json";
import enClients from "@/locales/en/clients.json";
import enCommon from "@/locales/en/common.json";
import enProjects from "@/locales/en/projects.json";
import itChat from "@/locales/it/chat.json";
import itClients from "@/locales/it/clients.json";
import itCommon from "@/locales/it/common.json";
import itProjects from "@/locales/it/projects.json";

export const SUPPORTED_LANGUAGES = ["it", "en"] as const;
export type Language = (typeof SUPPORTED_LANGUAGES)[number];

const STORAGE_KEY = "delir-language";

function initialLanguage(): Language {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "it" || stored === "en") return stored;
  } catch {
    /* localStorage unavailable */
  }
  return "it";
}

/**
 * Le traduzioni del canvas e della Simulazione, caricate quando servono.
 *
 * `process.json` da solo e' quasi tre quarti di tutte le stringhe, e stava nel
 * pacchetto d'ingresso in entrambe le lingue: chi apriva Clienti scaricava le
 * etichette della Simulazione in italiano e in inglese prima di vedere la
 * tabella. Le schermate che lo usano lo chiedono insieme al proprio codice
 * (`src/app/screens.tsx`), quindi non aggiunge un'attesa alla loro apertura.
 */
const processBundles = import.meta.glob<{ default: Record<string, unknown> }>(
  "../../locales/*/process.json",
);

const lazyNamespaces: BackendModule = {
  type: "backend",
  init() {},
  read(language, namespace, callback) {
    const load = namespace === "process" ? processBundles[`../../locales/${language}/process.json`] : undefined;
    if (!load) {
      callback(null, {});
      return;
    }
    load().then(
      (bundle) => callback(null, bundle.default),
      (error: unknown) => callback(error instanceof Error ? error : new Error(String(error)), false),
    );
  },
};

export const i18n = i18next.createInstance();

const initialized = i18n.use(lazyNamespaces).use(initReactI18next).init({
  resources: {
    it: {
      common: itCommon,
      projects: itProjects,
      clients: itClients,
      chat: itChat,
    },
    en: {
      common: enCommon,
      projects: enProjects,
      clients: enClients,
      chat: enChat,
    },
  },
  // Le lingue qui sopra sono parziali: quello che manca (`process`) lo porta
  // `lazyNamespaces` alla prima richiesta.
  partialBundledLanguages: true,
  ns: ["common", "projects", "clients", "chat"],
  lng: initialLanguage(),
  fallbackLng: "it",
  defaultNS: "common",
  interpolation: { escapeValue: false },
});

/**
 * Porta giu' le traduzioni di canvas e Simulazione per la lingua corrente.
 *
 * Aspetta la fine di `init`: prima la lingua non e' ancora decisa e
 * `loadNamespaces` risolverebbe senza aver caricato niente.
 *
 * Rifiuta se il file non arriva. La promessa di `loadNamespaces` si risolve
 * comunque (l'errore va solo alla callback), e chi la aspettava apriva la
 * schermata con le chiavi al posto delle parole invece di dire che non e'
 * riuscito a caricarla.
 *
 * Dopo un fallimento i18next segna `process` come fallito e alle richieste
 * successive lo salta, risolvendo senza leggere: un "Riprova" non avrebbe
 * riprovato niente. Lo stato fallito si dimentica prima di chiedere (puo'
 * averlo lasciato un cambio di lingua, che carica senza passare da qui), e si
 * risolve solo con il file della lingua corrente davvero in memoria.
 */
export function loadProcessTranslations(): Promise<void> {
  return initialized.then(
    () =>
      new Promise<void>((resolve, reject) => {
        forgetFailedProcessLoads();
        void i18n.loadNamespaces("process", (error) => {
          if (!error && i18n.hasResourceBundle(i18n.language, "process")) {
            resolve();
            return;
          }
          forgetFailedProcessLoads();
          reject(new Error("process translations not loaded", { cause: error ?? undefined }));
        });
      }),
  );
}

function forgetFailedProcessLoads(): void {
  const state = (i18n.services.backendConnector as { state?: Record<string, number> }).state ?? {};
  for (const name of Object.keys(state)) {
    if (name.endsWith("|process") && state[name] < 0) delete state[name];
  }
}

i18n.on("languageChanged", (lng) => {
  try {
    window.localStorage.setItem(STORAGE_KEY, lng);
  } catch {
    /* ignore */
  }
  document.documentElement.lang = lng;
});

document.documentElement.lang = i18n.language;
