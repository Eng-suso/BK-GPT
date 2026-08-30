import React from "react";
import ReactDOM from "react-dom/client";

// Fonts (self-hosted, replaces the Inter <link> in index.html)
import "@fontsource-variable/geist";
import "@fontsource-variable/geist-mono";

// Design token system — order matters: primitive -> semantic -> Tailwind bridge -> legacy
import "../styles/tokens/primitive.css";
import "../styles/tokens/semantic.css";
import "./styles/theme.css";
import "./styles/app-shell.css";

import { AppProviders } from "./app/providers";

const rootElement = document.getElementById("root");
if (rootElement) {
  ReactDOM.createRoot(rootElement).render(
    <React.StrictMode>
      <AppProviders />
    </React.StrictMode>,
  );
}
