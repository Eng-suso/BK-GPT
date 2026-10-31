import { DelirLogo } from "@/components/brand/DelirLogo";
import { HelpCircle, Settings } from "lucide-react";
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";
import { shellSections } from "./sections";
import type { ShellSection } from "./types";

export type GlobalSidebarProps = {
  compact?: boolean;
  /** Dentro il cassetto del telefono: etichette sempre visibili. */
  drawer?: boolean;
  className?: string;
  /** `null` quando la pagina aperta non e' una sezione (es. impostazioni). */
  activeSection: ShellSection | null;
  onSectionChange: (section: ShellSection) => void;
  /** Se la pagina aperta e' quella delle impostazioni. */
  settingsActive?: boolean;
  onOpenHelp: () => void;
  onOpenSettings: () => void;
};

/**
 * Renders the primary navigation sidebar with responsive compact and expanded layouts.
 *
 * @param compact - Whether to keep the sidebar icon-focused across all viewport sizes
 * @param activeSection - The currently selected navigation section
 * @param onSectionChange - Called with the selected section when a navigation item is clicked
 * @returns The rendered primary navigation sidebar
 */
export function GlobalSidebar({
  compact = false,
  drawer = false,
  className,
  activeSection,
  onSectionChange,
  settingsActive = false,
  onOpenHelp,
  onOpenSettings,
}: GlobalSidebarProps): React.JSX.Element {
  const { t } = useTranslation("common");
  // Il rail mostra le etichette solo da lg in su; il cassetto sempre.
  const expanded = drawer ? "justify-start px-2.5" : !compact && "lg:justify-start lg:px-2.5";
  const label = drawer ? "inline" : compact ? "hidden" : "hidden lg:inline";

  return (
    <aside
      aria-label={t("nav.primary")}
      className={cn("app-chrome app-sidebar flex flex-col items-center border-r px-2 py-5", drawer ? "h-full items-stretch px-3" : !compact && "lg:items-stretch lg:px-3", className)}
    >
      <div className="pb-7 pt-1 lg:px-2">
        {drawer ? <DelirLogo /> : <>
          <DelirLogo compact className={compact ? "" : "lg:hidden"} />
          <DelirLogo className={compact ? "hidden" : "hidden lg:inline-flex"} />
        </>}
      </div>

      <nav className="flex w-full flex-col gap-1">
        {shellSections.map((item) => {
          const Icon = item.icon;
          const isActive = item.id === activeSection;
          return (
            <button
              key={item.id}
              type="button"
              aria-current={isActive ? "page" : undefined}
              title={t(item.labelKey)}
              onClick={() => onSectionChange(item.id)}
              className={cn(
                "ui-nav-item relative flex h-11 items-center justify-center gap-3 rounded-full text-sm font-normal text-muted-foreground transition-colors duration-150 motion-reduce:transition-none",
                expanded,
                "hover:bg-muted/70 hover:text-foreground active:bg-muted focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2",
                isActive &&
                  "font-medium text-foreground",
              )}
            >
              <Icon
                className={cn(
                  "size-[17px] shrink-0",
                  isActive ? "text-primary" : "opacity-80",
                )}
                strokeWidth={1.6}
              />
              <span className={label}>{t(item.labelKey)}</span>
            </button>
          );
        })}
      </nav>

      <div className="mt-auto flex w-full flex-col gap-0.5 border-t border-border/70 pt-2.5">
        <button
          type="button"
          title={t("nav.help")}
          aria-haspopup="dialog"
          onClick={onOpenHelp}
          className={cn("ui-nav-item flex h-11 items-center justify-center gap-3 rounded-lg text-sm text-muted-foreground transition-colors duration-150 hover:bg-muted/70 hover:text-foreground active:bg-muted focus-visible:outline-2 focus-visible:outline-ring motion-reduce:transition-none", expanded)}
        >
          <HelpCircle className="size-[17px] shrink-0 opacity-70" strokeWidth={1.6} />
          <span className={label}>{t("nav.help")}</span>
        </button>
        <button
          type="button"
          title={t("nav.profile")}
          aria-current={settingsActive ? "page" : undefined}
          onClick={onOpenSettings}
          className={cn(
            "ui-nav-item flex h-11 items-center justify-center gap-3 rounded-lg text-sm text-muted-foreground transition-colors duration-150 hover:bg-muted/70 hover:text-foreground active:bg-muted focus-visible:outline-2 focus-visible:outline-ring motion-reduce:transition-none",
            expanded,
            settingsActive && "font-medium text-primary",
          )}
        >
          <Settings className={cn("size-[17px] shrink-0", settingsActive ? "opacity-100" : "opacity-70")} strokeWidth={1.6} />
          <span className={label}>{t("nav.profile")}</span>
        </button>
      </div>
    </aside>
  );
}
