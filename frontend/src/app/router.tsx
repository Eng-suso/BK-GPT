import { createBrowserRouter, Navigate } from "react-router-dom";

import { AppLayout } from "@/app/AppLayout";
import { DEFAULT_ROUTE } from "@/app/routes";
import { ArchivePage } from "@/features/archive/ArchivePage";
import { ClientsListPage } from "@/features/clients";
import { ConsultantPage } from "@/features/consultant/ConsultantPage";
import { HomePage } from "@/features/home/HomePage";
import { ModelsPage } from "@/features/models/ModelsPage";
import { ProcessStudioPage } from "@/features/process";
import {
  SimulationLayout,
  SimulationOverviewPage,
  ScenarioBuilderPage,
  ReplayPage,
  SimulationDashboardPage,
  HeatmapPage,
  ComparePage,
  InsightsPage,
} from "@/features/process/simulation";
import { ProjectsListPage, ProjectDetailPage } from "@/features/projects";

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
      { path: "*", element: <Navigate to={DEFAULT_ROUTE} replace /> },
    ],
  },
]);
