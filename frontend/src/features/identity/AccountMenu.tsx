import { useTranslation } from "react-i18next";
import { Building2, CircleUserRound, Settings, ShieldCheck, ShieldAlert } from "lucide-react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import { useIdentityQuery } from "./api";

export interface AccountMenuProps {
  compact?: boolean;
  /** Porta alle impostazioni, dove l'accesso e' spiegato per esteso. */
  onOpenSettings: () => void;
}

/**
 * Chi sta usando il prodotto, per quanto il backend lo sappia davvero.
 *
 * Qui c'era un nome scritto nel codice ("Marco Bianchi", "Admin"): davanti a un
 * cliente e' la prima cosa che si legge, e diceva una cosa falsa. Oggi il
 * backend non conosce persone: conosce lo spazio di lavoro e come la richiesta
 * e' stata autenticata. Il menu mostra quello, e dice apertamente che
 * l'identita' per persona non c'e' ancora, invece di inventarne una.
 */
export function AccountMenu({ compact = false, onOpenSettings }: AccountMenuProps): React.JSX.Element {
  const { t } = useTranslation("common");
  const identity = useIdentityQuery();
  const data = identity.data;

  const workspace = data?.tenantId ?? t(identity.isError ? "identity.unknown" : "identity.loading");
  // Quando l'identita' non si legge, "Non disponibile" si dice una volta sola:
  // ripeterlo sotto il nome dello spazio di lavoro non aggiunge niente.
  const accessLabel = data
    ? data.authEnabled
      ? t("identity.access.shared")
      : t("identity.access.open")
    : identity.isError
      ? null
      : t("identity.loading");

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label={t("identity.menuLabel", { workspace })}
          className="inline-flex shrink-0 items-center gap-2.5 rounded-lg py-[3px] pl-[3px] pr-1.5 hover:bg-muted/60 focus-visible:outline-2 focus-visible:outline-ring"
        >
          <span className="grid size-[30px] place-items-center rounded-full bg-muted text-muted-foreground ring-1 ring-black/5">
            <CircleUserRound className="size-4" strokeWidth={1.7} />
          </span>
          <span className={cn("hidden max-w-[160px] leading-tight", !compact && "lg:block")}>
            <span className="block truncate text-[12.5px] font-semibold">{workspace}</span>
            {accessLabel ? (
              <span className="block truncate text-[11px] text-muted-foreground">{accessLabel}</span>
            ) : null}
          </span>
        </button>
      </DropdownMenuTrigger>

      <DropdownMenuContent align="end" className="w-72">
        <DropdownMenuLabel className="flex items-start gap-2">
          <Building2 className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
          <span className="min-w-0">
            <span className="block text-[12.5px] font-semibold text-foreground">{workspace}</span>
            <span className="block text-[11.5px] font-normal text-muted-foreground">
              {t("identity.workspaceHint")}
            </span>
          </span>
        </DropdownMenuLabel>

        <DropdownMenuSeparator />

        <div className="flex items-start gap-2 px-2 py-1.5">
          {data?.authEnabled ? (
            <ShieldCheck
              className="mt-0.5 size-4 shrink-0 text-[var(--color-status-success)]"
              aria-hidden="true"
            />
          ) : (
            <ShieldAlert
              className="mt-0.5 size-4 shrink-0 text-[var(--color-status-warning)]"
              aria-hidden="true"
            />
          )}
          <span className="min-w-0">
            <span className="block text-[12.5px] text-foreground">
              {accessLabel ?? t("identity.unknown")}
            </span>
            <span className="block text-[11.5px] text-muted-foreground">
              {t("identity.noPersonYet")}
            </span>
          </span>
        </div>

        <DropdownMenuSeparator />

        <DropdownMenuItem onClick={onOpenSettings}>
          <Settings />
          {t("nav.profile")}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
