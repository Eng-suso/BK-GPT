const WORKSPACE_REFRESH_EVENT = "workspace:refresh";

export type WorkspaceRefreshDetail = {
  bpmnModelId?: string;
  forceCanvasReload?: boolean;
};

export function notifyWorkspaceChanged(detail: WorkspaceRefreshDetail = {}) {
  window.dispatchEvent(new CustomEvent<WorkspaceRefreshDetail>(WORKSPACE_REFRESH_EVENT, { detail }));
}

export function onWorkspaceChanged(callback: (detail: WorkspaceRefreshDetail) => void) {
  const handler = (event: Event) => {
    callback((event as CustomEvent<WorkspaceRefreshDetail>).detail || {});
  };

  window.addEventListener(WORKSPACE_REFRESH_EVENT, handler);
  return () => window.removeEventListener(WORKSPACE_REFRESH_EVENT, handler);
}
