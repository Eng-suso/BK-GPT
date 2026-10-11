import React from "react";
import ReactDOM from "react-dom/client";

// La pagina del cliente ha un suo ingresso: niente navigazione di DeliR e,
// soprattutto, niente codice con le credenziali dello studio (vedi
// `shareIsolation.test.ts`, che lo verifica a ogni giro di test).
import "@fontsource-variable/geist";
import "../../styles/tokens/primitive.css";
import "../../styles/tokens/semantic.css";
import "../styles/globals.css";
import "../styles/theme.css";
import "../styles/materials.css";
import { I18nextProvider } from "react-i18next";
import { i18n } from "@/lib/i18n";

import { SharedDashboardApp } from "./SharedDashboardApp";

const rootElement = document.getElementById("root");
if (rootElement) {
  ReactDOM.createRoot(rootElement).render(
    <React.StrictMode>
      <I18nextProvider i18n={i18n}>
        <SharedDashboardApp />
      </I18nextProvider>
    </React.StrictMode>,
  );
}
