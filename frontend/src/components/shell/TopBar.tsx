import { Menu, Search, PanelLeft } from "lucide-react";
import { useTranslation } from "react-i18next";

import { DelirLogo } from "@/components/brand/DelirLogo";
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
export function TopBar({ compact = false, navigationExpanded, onToggleNavigation, onOpenSearch, onNavigate, onOpenSettings, onOpenMobileNavigation, periodApplies = false }: { compact?: boolean; onOpenMobileNavigation?: () => void; periodApplies?: boolean; navigationExpanded?: boolean; onToggleNavigation?: () => void; onOpenSearch?: () => void; onNavigate?: (href: string) => void; onOpenSettings?: () => void } = {}): React.JSX.Element {
  const { t } = useTranslation("common");

  return (
    <header className="app-chrome app-topbar flex min-w-0 items-center gap-1 border-b px-2 sm:gap-3 sm:px-5">
      {/* Sul telefono la navigazione sta in un cassetto: un rail fisso si
          prendeva un sesto della larghezza a ogni schermata. */}
      {onOpenMobileNavigation && <button type="button" onClick={onOpenMobileNavigation} aria-label={t("nav.open")} aria-haspopup="dialog" className="ui-chrome-control md:hidden" ><Menu className="size-[18px]" strokeWidth={1.7} /></button>}
      {onOpenMobileNavigation && <DelirLogo className="text-lg md:hidden" />}
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
          "ui-search-bubble hidden h-9 min-w-0 max-w-[400px] flex-1 items-center gap-2 rounded-full border border-transparent px-3 text-left text-muted-foreground transition-colors duration-150 hover:border-border hover:bg-muted focus-visible:outline-2 focus-visible:outline-ring motion-reduce:transition-none",
          compact ? "xl:flex" : "md:flex",
        )}
      >
        <Search className="size-[15px] shrink-0" strokeWidth={1.8} />
        <span className="min-w-0 flex-1 truncate text-body-sm">{t("actions.search")}</span>
        <kbd className="hidden shrink-0 rounded border border-border bg-background px-1.5 py-0.5 font-mono text-micro lg:block">
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
          "ui-chrome-control",
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
