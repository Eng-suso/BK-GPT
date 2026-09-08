import { Bell, Building2, Calendar, ChevronDown, Search, PanelLeft } from "lucide-react";
import { useTranslation } from "react-i18next";

import { LanguageMenu } from "./LanguageMenu";
import { cn } from "@/lib/utils";

/**
 * Renders the product header with tenant, search, date-range, notification, language, and user controls.
 *
 * @param compact - Whether to use the compact layout.
 * @param navigationExpanded - Whether the navigation is expanded.
 * @param onToggleNavigation - Callback invoked when the navigation toggle is activated.
 * @returns The product header element.
 */
export function TopBar({ compact = false, navigationExpanded, onToggleNavigation }: { compact?: boolean; navigationExpanded?: boolean; onToggleNavigation?: () => void } = {}): React.JSX.Element {
  const { t } = useTranslation("common");
  const user = { name: "Marco Bianchi", role: "Admin", initials: "MB" };

  return (
    <header className="app-chrome flex min-w-0 items-center gap-2 border-b px-3 sm:gap-3.5">
      {onToggleNavigation && <button type="button" onClick={onToggleNavigation} aria-label={t("nav.toggle")} aria-expanded={navigationExpanded} className="hidden size-8 shrink-0 place-items-center rounded-md hover:bg-muted focus-visible:outline-2 focus-visible:outline-ring lg:grid"><PanelLeft className="size-4" /></button>}
      <button
        type="button"
        className="ui-button-glass inline-flex h-[34px] shrink-0 items-center gap-2 whitespace-nowrap rounded-full px-2.5 text-[13px] font-medium focus-visible:outline-2 focus-visible:outline-ring"
      >
        <Building2 className="size-4 text-muted-foreground" strokeWidth={1.7} />
        Gruppo DeliR
        <ChevronDown className="size-3 text-muted-foreground" />
      </button>

      <label className={cn("hidden h-[34px] min-w-0 max-w-[440px] flex-1 items-center gap-2 ui-field rounded-full px-3 text-muted-foreground focus-within:ring-2 focus-within:ring-ring", compact ? "xl:flex" : "md:flex")}>
        <Search className="size-[15px]" strokeWidth={1.8} />
        <input
          className="w-full bg-transparent text-[13px] text-foreground outline-none placeholder:text-muted-foreground"
          placeholder={t("actions.search")}
          aria-label={t("actions.search")}
        />
      </label>

      <div className="flex-1" />

      <div className={cn("hidden h-[34px] items-center gap-2 whitespace-nowrap ui-button-glass rounded-full px-2.5 text-[12.5px] font-medium text-muted-foreground", !compact && "xl:inline-flex")}>
        <Calendar className="size-3.5" strokeWidth={1.7} />
        01 mag – 31 lug 2024
        <ChevronDown className="size-3" />
      </div>

      <button
        type="button"
        aria-label="Notifiche"
        className="relative hidden size-[34px] shrink-0 place-items-center rounded-lg text-muted-foreground hover:bg-muted/60 sm:grid"
      >
        <Bell className="size-[17px]" strokeWidth={1.7} />
        <span className="absolute right-0.5 top-0.5 grid min-w-[15px] place-items-center rounded-full border-2 border-card bg-[var(--color-status-danger)] px-[3px] text-[9px] font-bold text-white">
          3
        </span>
      </button>

      <LanguageMenu />

      <button
        type="button"
        aria-label={user.name}
        className="inline-flex shrink-0 items-center gap-2.5 rounded-lg py-[3px] pl-[3px] pr-1.5 hover:bg-muted/60"
      >
        <span className="grid size-[30px] place-items-center rounded-full bg-muted text-[11px] font-semibold text-muted-foreground ring-1 ring-black/5">
          {user.initials}
        </span>
        <span className={cn("hidden leading-tight", !compact && "lg:block")}>
          <span className="block text-[12.5px] font-semibold">{user.name}</span>
          <span className="block text-[11px] text-muted-foreground">
            {user.role}
          </span>
        </span>
        <ChevronDown className="hidden size-3 text-muted-foreground sm:block" />
      </button>
    </header>
  );
}
