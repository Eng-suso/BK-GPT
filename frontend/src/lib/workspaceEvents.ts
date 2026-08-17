const WORKSPACE_REFRESH_EVENT = "workspace:refresh";

export function notifyWorkspaceChanged() {
  window.dispatchEvent(new Event(WORKSPACE_REFRESH_EVENT));
}

export function onWorkspaceChanged(callback: () => void) {
  window.addEventListener(WORKSPACE_REFRESH_EVENT, callback);
  return () => window.removeEventListener(WORKSPACE_REFRESH_EVENT, callback);
}
