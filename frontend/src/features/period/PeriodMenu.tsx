import { useTranslation } from "react-i18next";
import { Calendar, ChevronDown } from "lucide-react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import { usePeriod } from "./usePeriod";
import { PERIOD_IDS, localDate, periodRange, type PeriodId } from "./periods";

/** Le date del periodo sono date di calendario: si formattano come locali. */
function day(isoDate: string, locale: string): string {
  return new Intl.DateTimeFormat(locale || "it", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(localDate(isoDate));
}

export interface PeriodMenuProps {
  compact?: boolean;
}

/**
 * Il periodo di lavoro, nella barra in alto.
 *
 * Qui c'era un intervallo scritto nel codice ("01 mag – 31 lug 2024") che non
 * filtrava niente: accanto ai numeri diceva che quei numeri erano di quel
 * periodo, e non era vero. Ora e' una scelta, e le schermate che la rispettano
 * la dichiarano; dove non cambierebbe niente questa tendina non compare.
 */
export function PeriodMenu({ compact = false }: PeriodMenuProps): React.JSX.Element {
  const { t, i18n } = useTranslation("common");
  const { period, range, setPeriod } = usePeriod();
  const locale = i18n.language || "it";

  const label =
    period === "all"
      ? t("period.all")
      : range.from && range.to
        ? `${day(range.from, locale)} – ${day(range.to, locale)}`
        : t(`period.${period}`);

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label={t("period.label", { period: label })}
          // Visibile ovunque il periodo filtri: se una schermata mostra numeri
          // di un periodo, cambiarlo non puo' dipendere dalla larghezza dello
          // schermo. Sotto `md` resta l'icona, con l'intervallo nel menu.
          className={cn(
            "inline-flex h-[34px] max-w-[42vw] items-center gap-2 whitespace-nowrap ui-button-glass rounded-full px-2.5 text-[12.5px] font-medium text-muted-foreground focus-visible:outline-2 focus-visible:outline-ring",
            compact && "xl:max-w-none",
          )}
        >
          <Calendar className="size-3.5 shrink-0" strokeWidth={1.7} />
          <span className="hidden min-w-0 truncate md:inline">{label}</span>
          <ChevronDown className="size-3 shrink-0" />
        </button>
      </DropdownMenuTrigger>

      <DropdownMenuContent align="end" className="min-w-56">
        <DropdownMenuRadioGroup
          value={period}
          onValueChange={(value) => setPeriod(value as PeriodId)}
        >
        {PERIOD_IDS.map((id: PeriodId) => {
          const itemRange = periodRange(id);
          return (
            <DropdownMenuRadioItem key={id} value={id} className="text-[13px]">
              <span className="min-w-0">
                <span className="block">{t(`period.${id}`)}</span>
                {itemRange.from && itemRange.to ? (
                  <span className="block text-[11.5px] text-muted-foreground">
                    {day(itemRange.from, locale)} – {day(itemRange.to, locale)}
                  </span>
                ) : null}
              </span>
            </DropdownMenuRadioItem>
          );
        })}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
