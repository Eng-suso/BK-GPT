import { HelpCircle, Settings } from "lucide-react";
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";
import { shellSections } from "./sections";
import type { ShellSection } from "./types";

export type GlobalSidebarProps = {
  compact?: boolean;
  activeSection: ShellSection;
  onSectionChange: (section: ShellSection) => void;
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
  activeSection,
  onSectionChange,
}: GlobalSidebarProps): React.JSX.Element {
  const { t } = useTranslation("common");

  return (
    <aside
      aria-label={t("nav.primary")}
      className={cn("app-chrome flex flex-col items-center border-r px-2 py-4", !compact && "lg:items-stretch lg:px-3")}
    >
      <div className="pb-[18px] pt-1 text-[19px] font-bold tracking-[-0.03em] text-primary lg:px-2">
        <span className={compact ? "" : "lg:hidden"}>D</span>
        <span className={compact ? "hidden" : "hidden lg:inline"}>DeliR</span>
      </div>

      <nav className="flex w-full flex-col gap-0.5">
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
                "ui-nav-item relative flex h-10 items-center justify-center gap-[11px] rounded-2xl text-[13.5px] font-normal text-muted-foreground",
                !compact && "lg:justify-start lg:px-2.5",
                "hover:bg-white/70 hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring",
                isActive &&
                  "font-medium text-primary",
              )}
            >
              <Icon
                className={cn(
                  "size-[17px] shrink-0",
                  isActive ? "opacity-100" : "opacity-70",
                )}
                strokeWidth={1.6}
              />
              <span className={compact ? "hidden" : "hidden lg:inline"}>{t(item.labelKey)}</span>
            </button>
          );
        })}
      </nav>

      <div className="mt-auto flex w-full flex-col gap-0.5 border-t border-border/70 pt-2.5">
        <button
          type="button"
          title={t("nav.help")}
          className={cn("flex h-10 items-center justify-center gap-[11px] rounded-2xl text-[13.5px] text-muted-foreground hover:bg-white/70 hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring", !compact && "lg:justify-start lg:px-2.5")}
        >
          <HelpCircle className="size-[17px] shrink-0 opacity-70" strokeWidth={1.6} />
          <span className={compact ? "hidden" : "hidden lg:inline"}>{t("nav.help")}</span>
        </button>
        <button
          type="button"
          title={t("nav.profile")}
          className={cn("flex h-10 items-center justify-center gap-[11px] rounded-2xl text-[13.5px] text-muted-foreground hover:bg-white/70 hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring", !compact && "lg:justify-start lg:px-2.5")}
        >
          <Settings className="size-[17px] shrink-0 opacity-70" strokeWidth={1.6} />
          <span className={compact ? "hidden" : "hidden lg:inline"}>{t("nav.profile")}</span>
        </button>
      </div>
    </aside>
  );
}
