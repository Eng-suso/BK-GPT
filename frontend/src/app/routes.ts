import type { ShellSection } from "@/components/shell/types";

export const ROUTES = {
  home: "/home",
  consultant: "/consultant",
  clients: {
    list: "/clients",
    detail: (clientId: string) => `/clients/${clientId}`,
  },
  projects: {
    list: "/projects",
    detail: (projectId: string) => `/projects/${projectId}`,
    process: (projectId: string, processId: string) =>
      `/projects/${projectId}/processes/${processId}`,
    simulation: (
      projectId: string,
      processId: string,
      sub: string = "overview",
    ) => `/projects/${projectId}/processes/${processId}/simulation/${sub}`,
  },
  models: "/models",
  archive: "/archive",
} as const;

/** Landing route when no section is selected. */
export const DEFAULT_ROUTE = ROUTES.projects.list;

/** Sidebar section id -> top-level path. */
export const SECTION_PATH: Record<ShellSection, string> = {
  home: ROUTES.home,
  consultant: ROUTES.consultant,
  clients: ROUTES.clients.list,
  projects: ROUTES.projects.list,
  models: ROUTES.models,
  archive: ROUTES.archive,
};

export function sectionFromPath(pathname: string): ShellSection {
  const match = (Object.entries(SECTION_PATH) as [ShellSection, string][]).find(
    ([, path]) => pathname === path || pathname.startsWith(`${path}/`),
  );
  return match?.[0] ?? "projects";
}
