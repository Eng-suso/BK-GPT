import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";

// Design Token System — Source of Truth
// Order matters: primitive → semantic → component/layout CSS
import "../styles/tokens/primitive.css";
import "../styles/tokens/semantic.css";
import "./styles/app-shell.css";

const rootElement = document.getElementById("root");
if (rootElement) {
  ReactDOM.createRoot(rootElement).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>
  );
}
