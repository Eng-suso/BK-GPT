import { Bell, Building2, Calendar, ChevronDown, Search } from "lucide-react";
import { useTranslation } from "react-i18next";

import { LanguageMenu } from "./LanguageMenu";

/**
 * Product top bar. Tenant / global search / date-range / notifications / user.
 * Controls are presentational for now — wired in a later step.
 */
export function TopBar(): React.JSX.Element {
  const { t } = useTranslation("common");
  const user = { name: "Marco Bianchi", role: "Admin", initials: "MB" };

  return (
    <header className="flex items-center gap-3.5 border-b border-border bg-card px-5">
      <button
        type="button"
        className="inline-flex h-[34px] items-center gap-2 rounded-lg border border-border px-2.5 text-[13px] font-medium shadow-[0_1px_2px_rgba(14,20,32,0.05)]"
      >
        <Building2 className="size-4 text-muted-foreground" strokeWidth={1.7} />
        Gruppo DeliR
        <ChevronDown className="size-3 text-muted-foreground" />
      </button>

      <label className="flex h-[34px] max-w-[440px] flex-1 items-center gap-2 rounded-lg border border-border bg-[var(--color-surface-secondary)] px-3 text-muted-foreground">
        <Search className="size-[15px]" strokeWidth={1.8} />
        <input
          className="w-full bg-transparent text-[13px] text-foreground outline-none placeholder:text-muted-foreground"
          placeholder={t("actions.search")}
          aria-label={t("actions.search")}
        />
      </label>

      <div className="flex-1" />

      <div className="inline-flex h-[34px] items-center gap-2 rounded-lg border border-border px-2.5 text-[12.5px] font-medium text-muted-foreground shadow-[0_1px_2px_rgba(14,20,32,0.05)]">
        <Calendar className="size-3.5" strokeWidth={1.7} />
        01 mag – 31 lug 2024
        <ChevronDown className="size-3" />
      </div>

      <button
        type="button"
        aria-label="Notifiche"
        className="relative grid size-[34px] place-items-center rounded-lg text-muted-foreground hover:bg-muted/60"
      >
        <Bell className="size-[17px]" strokeWidth={1.7} />
        <span className="absolute right-0.5 top-0.5 grid min-w-[15px] place-items-center rounded-full border-2 border-card bg-[var(--color-status-danger)] px-[3px] text-[9px] font-bold text-white">
          3
        </span>
      </button>

      <LanguageMenu />

      <button
        type="button"
        className="inline-flex items-center gap-2.5 rounded-lg py-[3px] pl-[3px] pr-1.5 hover:bg-muted/60"
      >
        <span className="grid size-[30px] place-items-center rounded-full bg-muted text-[11px] font-semibold text-muted-foreground ring-1 ring-black/5">
          {user.initials}
        </span>
        <span className="leading-tight">
          <span className="block text-[12.5px] font-semibold">{user.name}</span>
          <span className="block text-[11px] text-muted-foreground">
            {user.role}
          </span>
        </span>
        <ChevronDown className="size-3 text-muted-foreground" />
      </button>
    </header>
  );
}
