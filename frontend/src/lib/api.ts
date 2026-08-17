const configuredApiBase =
  (window as any).DELIR_API_BASE ||
  (window as any).SUSO_API_BASE ||
  import.meta.env.VITE_API_BASE_URL;

const isBackendHost =
  window.location.hostname === "127.0.0.1" &&
  window.location.port === "8000";

export const API_BASE =
  configuredApiBase ||
  (window.location.protocol === "file:" || !isBackendHost ? "http://127.0.0.1:8000" : "");
