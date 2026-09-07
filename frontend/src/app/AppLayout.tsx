import { useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";

import { GlobalSidebar } from "@/components/shell/GlobalSidebar";
import { TopBar } from "@/components/shell/TopBar";
import { Toaster } from "@/ui/sonner";
import { SECTION_PATH, sectionFromPath } from "@/app/routes";
import { cn } from "@/lib/utils";

/**
 * Renders the application shell with route-aware navigation and routed content.
 */
export function AppLayout(): React.JSX.Element {
  const location = useLocation();
  const navigate = useNavigate();
  const activeSection = sectionFromPath(location.pathname);
  const isStudio = location.pathname.includes("/processes/");
  const [expandedStudioNav, setExpandedStudioNav] = useState(false);
  const compactNav = isStudio && !expandedStudioNav;

  return (
    <>
    <div className={cn("grid h-dvh grid-cols-[60px_minmax(0,1fr)] overflow-hidden bg-background text-foreground", !compactNav && "lg:grid-cols-[212px_minmax(0,1fr)]")}>
      <GlobalSidebar
        compact={compactNav}
        activeSection={activeSection}
        onSectionChange={(section) => navigate(SECTION_PATH[section])}
      />
      <div className={cn("grid min-w-0 grid-cols-[minmax(0,1fr)] overflow-hidden", isStudio ? "grid-rows-[48px_minmax(0,1fr)]" : "grid-rows-[60px_minmax(0,1fr)]")}>
        <TopBar compact={isStudio} navigationExpanded={!compactNav} onToggleNavigation={isStudio ? () => setExpandedStudioNav((value) => !value) : undefined} />
        <main className="min-h-0 overflow-hidden">
          <Outlet />
        </main>
      </div>
    </div>
    {/* Le conferme di salvataggio vivono sopra ogni schermata: un form che si
        chiude senza dire cosa ha scritto lascia il consulente a verificarlo
        nella lista. Fuori dalla griglia della shell, non dentro: come figlio
        della griglia il suo `<section>` prendeva una riga implicita e
        schiacciava di 125px sidebar e contenuto. */}
    <Toaster position="bottom-right" />
    </>
  );
}
