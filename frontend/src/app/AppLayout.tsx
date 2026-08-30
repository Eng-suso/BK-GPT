import { Outlet, useLocation, useNavigate } from "react-router-dom";

import { GlobalSidebar } from "@/components/shell/GlobalSidebar";
import { TopBar } from "@/components/shell/TopBar";
import { SECTION_PATH, sectionFromPath } from "@/app/routes";

export function AppLayout(): React.JSX.Element {
  const location = useLocation();
  const navigate = useNavigate();
  const activeSection = sectionFromPath(location.pathname);

  return (
    <div className="grid h-dvh grid-cols-[60px_minmax(0,1fr)] overflow-hidden bg-background text-foreground lg:grid-cols-[212px_minmax(0,1fr)]">
      <GlobalSidebar
        activeSection={activeSection}
        onSectionChange={(section) => navigate(SECTION_PATH[section])}
      />
      <div className="grid grid-rows-[60px_minmax(0,1fr)] overflow-hidden">
        <TopBar />
        <main className="min-h-0 overflow-hidden">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
