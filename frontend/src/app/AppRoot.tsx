import React, { useState } from "react";
import { AppShell } from "../components/shell/AppShell";
import type { ShellSection } from "../components/shell/types";
import { ArchivePage } from "../features/archive/ArchivePage";
import { ClientsPage } from "../features/clients/ClientsPage";
import { ConsultantPage } from "../features/consultant/ConsultantPage";
import { HomePage } from "../features/home/HomePage";
import { ModelsPage } from "../features/models/ModelsPage";
import { ProjectsPage } from "../features/projects/ProjectsPage";

export const AppRoot: React.FC = () => {
  const [activeSection, setActiveSection] = useState<ShellSection>("projects");

  return (
    <AppShell activeSection={activeSection} onSectionChange={setActiveSection}>
      {renderSection(activeSection)}
    </AppShell>
  );
};

function renderSection(section: ShellSection) {
  if (section === "home") return <HomePage />;
  if (section === "clients") return <ClientsPage />;
  if (section === "projects") return <ProjectsPage />;
  if (section === "models") return <ModelsPage />;
  if (section === "archive") return <ArchivePage />;
  return <ConsultantPage />;
}
