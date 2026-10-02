import { Search, PanelLeft } from "lucide-react";
import { useTranslation } from "react-i18next";

import { AccountMenu } from "@/features/identity/AccountMenu";
import { PeriodMenu } from "@/features/period/PeriodMenu";
import { NotificationsMenu } from "@/features/notifications/NotificationsMenu";
import { LanguageMenu } from "./LanguageMenu";
import { searchShortcutLabel } from "./shortcuts";
import { cn } from "@/lib/utils";

/**
 * Renders the product header with tenant, search, date-range, notification, language, and user controls.
 *
 * @param compact - Whether to use the compact layout.
 * @param navigationExpanded - Whether the navigation is expanded.
 * @param onToggleNavigation - Callback invoked when the navigation toggle is activated.
 * @returns The product header element.
 */
export function TopBar({ compact = false, navigationExpanded, onToggleNavigation, onOpenSearch, onNavigate, onOpenSettings, periodApplies = false }: { compact?: boolean; periodApplies?: boolean; navigationExpanded?: boolean; onToggleNavigation?: () => void; onOpenSearch?: () => void; onNavigate?: (href: string) => void; onOpenSettings?: () => void } = {}): React.JSX.Element {
  const { t } = useTranslation("common");

  return (
    <header className="app-chrome flex min-w-0 items-center gap-2 border-b px-3 sm:gap-3.5">
      {onToggleNavigation && <button type="button" onClick={onToggleNavigation} aria-label={t("nav.toggle")} aria-expanded={navigationExpanded} className="hidden size-8 shrink-0 place-items-center rounded-md hover:bg-muted focus-visible:outline-2 focus-visible:outline-ring lg:grid"><PanelLeft className="size-4" /></button>}
      {/* Un bottone e non un campo: la ricerca vive in un pannello che sa
          raggruppare i risultati e si percorre da tastiera. Un input qui
          sembrerebbe cercare nella pagina, che non e' cio' che fa. */}
      <button
        type="button"
        onClick={onOpenSearch}
        aria-haspopup="dialog"
        aria-keyshortcuts="Control+K Meta+K"
        className={cn(
          "hidden h-[34px] min-w-0 max-w-[440px] flex-1 items-center gap-2 ui-field rounded-full px-3 text-left text-muted-foreground focus-visible:outline-2 focus-visible:outline-ring",
          compact ? "xl:flex" : "md:flex",
        )}
      >
        <Search className="size-[15px] shrink-0" strokeWidth={1.8} />
        <span className="min-w-0 flex-1 truncate text-[13px]">{t("actions.search")}</span>
        <kbd className="hidden shrink-0 rounded border border-border px-1.5 py-0.5 font-mono text-[10px] lg:block">
          {searchShortcutLabel()}
        </kbd>
      </button>

      {/* Sotto il breakpoint del campo resta la lente: la ricerca non sparisce
          sui viewport stretti, dove serve di piu'. */}
      <button
        type="button"
        onClick={onOpenSearch}
        aria-haspopup="dialog"
        aria-label={t("actions.search")}
        className={cn(
          "grid size-[34px] shrink-0 place-items-center rounded-lg text-muted-foreground hover:bg-muted/60 focus-visible:outline-2 focus-visible:outline-ring",
          compact ? "xl:hidden" : "md:hidden",
        )}
      >
        <Search className="size-[17px]" strokeWidth={1.7} />
      </button>

      <div className="flex-1" />

      {periodApplies ? <PeriodMenu compact={compact} /> : null}

      <NotificationsMenu onNavigate={onNavigate ?? (() => {})} />

      <LanguageMenu />

      <AccountMenu compact={compact} onOpenSettings={onOpenSettings ?? (() => {})} />
    </header>
  );
}
