import { useTranslation } from "react-i18next";
import { Calendar, ChevronDown, Check } from "lucide-react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import { formatDate } from "@/lib/date";
import { usePeriod } from "./usePeriod";
import { PERIOD_IDS, periodRange, type PeriodId } from "./periods";

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
        ? `${formatDate(range.from, locale)} – ${formatDate(range.to, locale)}`
        : t(`period.${period}`);

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label={t("period.label", { period: label })}
          className={cn(
            "hidden h-[34px] items-center gap-2 whitespace-nowrap ui-button-glass rounded-full px-2.5 text-[12.5px] font-medium text-muted-foreground focus-visible:outline-2 focus-visible:outline-ring",
            !compact && "xl:inline-flex",
          )}
        >
          <Calendar className="size-3.5" strokeWidth={1.7} />
          {label}
          <ChevronDown className="size-3" />
        </button>
      </DropdownMenuTrigger>

      <DropdownMenuContent align="end" className="min-w-56">
        {PERIOD_IDS.map((id: PeriodId) => {
          const itemRange = periodRange(id);
          return (
            <DropdownMenuItem
              key={id}
              onClick={() => setPeriod(id)}
              className="flex items-start gap-2 text-[13px]"
            >
              <Check
                className={cn("mt-0.5 size-3.5 shrink-0", id !== period && "opacity-0")}
                aria-hidden="true"
              />
              <span className="min-w-0">
                <span className="block">{t(`period.${id}`)}</span>
                {itemRange.from && itemRange.to ? (
                  <span className="block text-[11.5px] text-muted-foreground">
                    {formatDate(itemRange.from, locale)} – {formatDate(itemRange.to, locale)}
                  </span>
                ) : null}
              </span>
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
