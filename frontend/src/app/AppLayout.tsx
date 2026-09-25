import { Suspense, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";

import { ErrorBoundary } from "@/components/feedback";
import { GlobalSidebar } from "@/components/shell/GlobalSidebar";
import { HelpDialog } from "@/components/shell/HelpDialog";
import { TopBar } from "@/components/shell/TopBar";
import { ServiceStatusDialog } from "@/features/status/ServiceStatusDialog";
import { Skeleton } from "@/ui/skeleton";
import { Toaster } from "@/ui/sonner";
import { ROUTES, SECTION_PATH, isSettingsPath, sectionFromPath } from "@/app/routes";
import { useWorkspaceRefresh } from "@/lib/hooks/useWorkspaceRefresh";
import { cn } from "@/lib/utils";

/**
 * Renders the application shell with route-aware navigation, routed content, and global notifications.
 */
export function AppLayout(): React.JSX.Element {
  // Un solo iscritto a `workspace:refresh`, sopra tutte le rotte. Stava sulle
  // tre pagine di lista, e le pagine che ospitano una chat non erano fra
  // quelle: la Project Chat registrava un processo, l'evento partiva e nessuno
  // sulla pagina lo ascoltava, quindi il record nuovo non compariva finche'
  // non si navigava via e si tornava.
  useWorkspaceRefresh();

  const location = useLocation();
  const navigate = useNavigate();
  const settingsActive = isSettingsPath(location.pathname);
  const activeSection = settingsActive ? null : sectionFromPath(location.pathname);
  const isStudio = location.pathname.includes("/processes/");
  const [expandedStudioNav, setExpandedStudioNav] = useState(false);
  const compactNav = isStudio && !expandedStudioNav;
  const [isHelpOpen, setIsHelpOpen] = useState(false);
  const [isStatusOpen, setIsStatusOpen] = useState(false);

  return (
    <>
    <div className={cn("app-material grid h-dvh grid-cols-[60px_minmax(0,1fr)] overflow-hidden text-foreground", !compactNav && "lg:grid-cols-[212px_minmax(0,1fr)]")}>
      <GlobalSidebar
        compact={compactNav}
        activeSection={activeSection}
        onSectionChange={(section) => navigate(SECTION_PATH[section])}
        settingsActive={settingsActive}
        onOpenHelp={() => setIsHelpOpen(true)}
        onOpenSettings={() => navigate(ROUTES.settings)}
      />
      <div className={cn("grid min-w-0 grid-cols-[minmax(0,1fr)] overflow-hidden", isStudio ? "grid-rows-[48px_minmax(0,1fr)]" : "grid-rows-[60px_minmax(0,1fr)]")}>
        <TopBar compact={isStudio} navigationExpanded={!compactNav} onToggleNavigation={isStudio ? () => setExpandedStudioNav((value) => !value) : undefined} />
        <main className="min-h-0 overflow-hidden">
          {/* La rete sta qui dentro e non intorno alla shell: una schermata che
              si ferma non deve portarsi via navigazione, ricerca e chat. La
              chiave è il percorso, così andare altrove ripulisce l'errore
              invece di lasciarlo appeso. */}
          <ErrorBoundary resetKey={location.pathname}>
            {/* Le schermate arrivano a richiesta: questo e' cosa si vede
                mentre il pezzo di prodotto sta arrivando. Uno scheletro e non
                una rotella, perche' la forma della schermata si conosce. */}
            <Suspense fallback={<ScreenLoading />}>
              <Outlet />
            </Suspense>
          </ErrorBoundary>
        </main>
      </div>
    </div>
    {/* Le conferme di salvataggio vivono sopra ogni schermata: un form che si
        chiude senza dire cosa ha scritto lascia il consulente a verificarlo
        nella lista. Fuori dalla griglia della shell, non dentro: come figlio
        della griglia il suo `<section>` prendeva una riga implicita e
        schiacciava di 125px sidebar e contenuto. */}
    <Toaster position="bottom-right" />
    <HelpDialog
      open={isHelpOpen}
      onOpenChange={setIsHelpOpen}
      onOpenProjects={() => navigate(ROUTES.projects.list)}
      onOpenServiceStatus={() => setIsStatusOpen(true)}
    />
    <ServiceStatusDialog open={isStatusOpen} onOpenChange={setIsStatusOpen} />
    </>
  );
}

/** Lo scheletro di una schermata che sta arrivando. */
function ScreenLoading(): React.JSX.Element {
  return (
    <div className="flex h-full flex-col gap-4 px-7 py-6" aria-busy="true">
      <Skeleton className="h-8 w-64" />
      <Skeleton className="h-4 w-96" />
      <Skeleton className="h-full w-full" />
    </div>
  );
}
