import { createBrowserRouter, Navigate } from "react-router-dom";

import { AppLayout } from "@/app/AppLayout";
import { DEFAULT_ROUTE } from "@/app/routes";
import { ArchivePage } from "@/features/archive/ArchivePage";
import { ClientsListPage } from "@/features/clients";
import { ConsultantPage } from "@/features/consultant/ConsultantPage";
import { HomePage } from "@/features/home/HomePage";
import { ModelsPage } from "@/features/models/ModelsPage";
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
      { path: "models", element: <ModelsPage /> },
      { path: "archive", element: <ArchivePage /> },
      { path: "*", element: <Navigate to={DEFAULT_ROUTE} replace /> },
    ],
  },
]);
