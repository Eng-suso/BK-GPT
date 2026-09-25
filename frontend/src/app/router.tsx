import { createBrowserRouter, Navigate } from "react-router-dom";

import { AppLayout } from "@/app/AppLayout";
import { NotFoundPage } from "@/app/NotFoundPage";
import { DEFAULT_ROUTE } from "@/app/routes";
import {
  ArchivePage,
  ClientsListPage,
  ComparePage,
  ConsultantPage,
  HeatmapPage,
  HomePage,
  InsightsPage,
  ModelsPage,
  ProcessStudioPage,
  ProjectDetailPage,
  ProjectsListPage,
  ReplayPage,
  ScenarioBuilderPage,
  SettingsPage,
  SimulationDashboardPage,
  SimulationLayout,
  SimulationOverviewPage,
} from "@/app/screens";

/**
 * Library-mode router. Data is owned by TanStack Query, not RR loaders.
 * `/projects` is migrated (Step 6); the other routes still mount the
 * pre-migration feature pages, swapped one at a time.
 */
export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [
      { index: true, element: <Navigate to={DEFAULT_ROUTE} replace /> },
      { path: "home", element: <HomePage /> },
      { path: "consultant", element: <ConsultantPage /> },
      { path: "clients", element: <ClientsListPage /> },
      { path: "projects", element: <ProjectsListPage /> },
      { path: "projects/:projectId", element: <ProjectDetailPage /> },
      {
        path: "projects/:projectId/processes/:processId",
        element: <ProcessStudioPage />,
      },
      {
        path: "projects/:projectId/processes/:processId/simulation",
        element: <SimulationLayout />,
        children: [
          { index: true, element: <Navigate to="overview" replace /> },
          { path: "overview", element: <SimulationOverviewPage /> },
          { path: "scenario", element: <ScenarioBuilderPage /> },
          { path: "replay", element: <ReplayPage /> },
          { path: "replay/:runId", element: <ReplayPage /> },
          { path: "dashboard", element: <SimulationDashboardPage /> },
          { path: "dashboard/:runId", element: <SimulationDashboardPage /> },
          { path: "heatmap", element: <HeatmapPage /> },
          { path: "heatmap/:runId", element: <HeatmapPage /> },
          { path: "compare", element: <ComparePage /> },
          { path: "insights", element: <InsightsPage /> },
          { path: "insights/:runId", element: <InsightsPage /> },
        ],
      },
      { path: "models", element: <ModelsPage /> },
      { path: "archive", element: <ArchivePage /> },
      { path: "settings", element: <SettingsPage /> },
      // Non un `Navigate`: un indirizzo che non esiste lo dice, e resta nella
      // cronologia, cosi' il tasto indietro torna da dove si veniva.
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);
