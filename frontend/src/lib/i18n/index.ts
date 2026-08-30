import i18next from "i18next";
import { initReactI18next } from "react-i18next";

import enClients from "@/locales/en/clients.json";
import enCommon from "@/locales/en/common.json";
import enProcess from "@/locales/en/process.json";
import enProjects from "@/locales/en/projects.json";
import itClients from "@/locales/it/clients.json";
import itCommon from "@/locales/it/common.json";
import itProcess from "@/locales/it/process.json";
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

export const i18n = i18next.createInstance();

void i18n.use(initReactI18next).init({
  resources: {
    it: {
      common: itCommon,
      projects: itProjects,
      clients: itClients,
      process: itProcess,
    },
    en: {
      common: enCommon,
      projects: enProjects,
      clients: enClients,
      process: enProcess,
    },
  },
  ns: ["common", "projects", "clients", "process"],
  lng: initialLanguage(),
  fallbackLng: "it",
  defaultNS: "common",
  interpolation: { escapeValue: false },
});

i18n.on("languageChanged", (lng) => {
  try {
    window.localStorage.setItem(STORAGE_KEY, lng);
  } catch {
    /* ignore */
  }
  document.documentElement.lang = lng;
});

document.documentElement.lang = i18n.language;
