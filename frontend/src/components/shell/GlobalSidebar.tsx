import { HelpCircle, Settings } from "lucide-react";
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";
import { shellSections } from "./sections";
import type { ShellSection } from "./types";

export type GlobalSidebarProps = {
  activeSection: ShellSection;
  onSectionChange: (section: ShellSection) => void;
};

export function GlobalSidebar({
  activeSection,
  onSectionChange,
}: GlobalSidebarProps): React.JSX.Element {
  const { t } = useTranslation("common");

  return (
    <aside
      aria-label={t("nav.primary")}
      className="flex flex-col items-center border-r border-border bg-card px-2 py-4 lg:items-stretch lg:px-3"
    >
      <div className="pb-[18px] pt-1 text-[19px] font-bold tracking-[-0.03em] text-primary lg:px-2">
        <span className="lg:hidden">D</span>
        <span className="hidden lg:inline">DeliR</span>
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
                "relative flex h-9 items-center justify-center gap-[11px] rounded-[7px] text-[13.5px] font-normal text-muted-foreground lg:justify-start lg:px-2.5",
                "hover:bg-muted/60 hover:text-foreground",
                isActive &&
                  "bg-[var(--color-surface-selected)] font-medium text-primary lg:before:absolute lg:before:-left-3 lg:before:inset-y-2 lg:before:w-[3px] lg:before:rounded-r-[3px] lg:before:bg-primary lg:before:content-['']",
              )}
            >
              <Icon
                className={cn(
                  "size-[17px] shrink-0",
                  isActive ? "opacity-100" : "opacity-70",
                )}
                strokeWidth={1.6}
              />
              <span className="hidden lg:inline">{t(item.labelKey)}</span>
            </button>
          );
        })}
      </nav>

      <div className="mt-auto flex w-full flex-col gap-0.5 border-t border-border/70 pt-2.5">
        <button
          type="button"
          title={t("nav.help")}
          className="flex h-9 items-center justify-center gap-[11px] rounded-[7px] text-[13.5px] text-muted-foreground hover:bg-muted/60 hover:text-foreground lg:justify-start lg:px-2.5"
        >
          <HelpCircle className="size-[17px] shrink-0 opacity-70" strokeWidth={1.6} />
          <span className="hidden lg:inline">{t("nav.help")}</span>
        </button>
        <button
          type="button"
          title={t("nav.profile")}
          className="flex h-9 items-center justify-center gap-[11px] rounded-[7px] text-[13.5px] text-muted-foreground hover:bg-muted/60 hover:text-foreground lg:justify-start lg:px-2.5"
        >
          <Settings className="size-[17px] shrink-0 opacity-70" strokeWidth={1.6} />
          <span className="hidden lg:inline">{t("nav.profile")}</span>
        </button>
      </div>
    </aside>
  );
}
