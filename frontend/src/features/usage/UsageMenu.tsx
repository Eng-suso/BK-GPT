import { useTranslation } from "react-i18next";
import { Loader2 } from "lucide-react";

// Dal suo file, non dall indice: l indice porta con se' le tabelle (react-table)
// nel pacchetto d'ingresso, e la barra in alto e' nel pacchetto d'ingresso.
import { Meter, type MeterTone } from "@/components/data/Meter";
import { InlineNotice } from "@/components/feedback/InlineNotice";
import { Button } from "@/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/ui/popover";
import { daysUntil, formatDayMonth, formatUpcoming } from "@/lib/date";
import { headlineShare, usageTone, useUsageQuery, type ActiveUsage, type UsageWindow } from "./api";

// Gli stessi colori di `Meter`, per l'anello che non e' una barra.
const RING_COLOR: Record<MeterTone, string> = {
  ok: "var(--primary)",
  warning: "var(--color-status-warning)",
  danger: "var(--color-status-danger)",
};

/** Percentuale intera per le persone: 0,4% si legge "1%", non "0%" (qualcosa e' stato usato). */
function percent(share: number): number {
  if (share <= 0) return 0;
  return Math.max(1, Math.min(100, Math.round(share * 100)));
}

/** La quota da mostrare: una finestra esaurita e' piena, qualunque sia l'arrotondamento. */
function shownShare(window: UsageWindow): number {
  return window.exhausted ? 1 : window.usedShare;
}

/**
 * L'anello della barra: la quota della finestra piu' vicina al limite.
 *
 * Un numero dentro un cerchio che si riempie: si legge a colpo d'occhio senza
 * aprire niente, e cambia colore prima che il limite arrivi, non dopo.
 */
export function UsageRing({ share, size = 28 }: { share: number; size?: number }): React.JSX.Element {
  const stroke = 3;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const value = percent(share);
  const center = size / 2;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true" className="block">
      <circle cx={center} cy={center} r={radius} fill="none" stroke="var(--border)" strokeWidth={stroke} />
      <circle
        cx={center}
        cy={center}
        r={radius}
        fill="none"
        stroke={RING_COLOR[usageTone(share)]}
        strokeWidth={stroke}
        strokeLinecap="round"
        strokeDasharray={circumference}
        strokeDashoffset={circumference * (1 - Math.min(1, share))}
        transform={`rotate(-90 ${center} ${center})`}
        className="transition-[stroke-dashoffset] duration-500 motion-reduce:transition-none"
      />
      <text
        x="50%"
        y="50%"
        dominantBaseline="central"
        textAnchor="middle"
        className="fill-foreground font-semibold tabular-nums"
        style={{ fontSize: value === 100 ? 8 : 9.5 }}
      >
        {value}
      </text>
    </svg>
  );
}

function WindowRow({ title, window, caption }: { title: string; window: UsageWindow; caption: string }): React.JSX.Element {
  const { t } = useTranslation("common");
  const share = shownShare(window);
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-border bg-card px-3 py-3">
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-body-sm font-semibold text-foreground">{title}</p>
        <p className="shrink-0 text-xs tabular-nums text-muted-foreground">
          {t("usage.used", { percent: percent(share) })}
        </p>
      </div>
      <Meter value={percent(share)} label={title} tone={usageTone(share)} showValue={false} height={8} />
      <p className="text-xs text-muted-foreground">{caption}</p>
    </div>
  );
}

/**
 * Il contatore d'uso della prova: anello nella barra, dettaglio nel pannello.
 *
 * Il consulente deve sapere quanto ha usato, quanto gli resta e quando si
 * ripristina, prima di trovarsi fermo. Con i limiti spenti l'anello non c'e':
 * un contatore che non conta niente sarebbe solo rumore.
 */
export function UsageMenu(): React.JSX.Element | null {
  const { t } = useTranslation("common");
  const usage = useUsageQuery();

  if (!usage.data?.enabled) return null;
  const share = headlineShare(usage.data);

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={t("usage.label", { percent: percent(share) })}
          className="ui-chrome-control"
        >
          <UsageRing share={share} />
        </button>
      </PopoverTrigger>

      <PopoverContent align="end" collisionPadding={16} className="w-[min(26rem,calc(100vw-2rem))] p-0">
        <div className="flex items-center justify-between gap-2 border-b border-border px-3 py-2">
          <p className="text-body-sm font-semibold text-foreground">{t("usage.title")}</p>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => void usage.refetch()}
            disabled={usage.isFetching}
            aria-label={t("usage.refresh")}
          >
            {usage.isFetching ? <Loader2 className="size-4 animate-spin" aria-hidden="true" /> : t("usage.refresh")}
          </Button>
        </div>
        <UsagePanel usage={usage.data} />
      </PopoverContent>
    </Popover>
  );
}

function UsagePanel({ usage }: { usage: ActiveUsage }): React.JSX.Element {
  const { t, i18n } = useTranslation("common");
  const locale = i18n.language || "it";
  const upcoming = (iso: string) =>
    formatUpcoming(iso, locale, {
      today: (time) => t("usage.when.today", { time }),
      tomorrow: (time) => t("usage.when.tomorrow", { time }),
      weekday: (day, time) => t("usage.when.weekday", { day, time }),
    });

  const sessionCaption = usage.session.resetsAt
    ? t("usage.session.resets", { when: upcoming(usage.session.resetsAt) })
    : t("usage.session.notStarted", { count: usage.sessionHours });
  const weekCaption = usage.week.resetsAt ? t("usage.week.resets", { when: upcoming(usage.week.resetsAt) }) : "";
  const trialCaption =
    usage.trialOver || !usage.trial.resetsAt
      ? t("usage.trial.over")
      : t("usage.trial.ends", { day: formatDayMonth(usage.trial.resetsAt, locale), count: daysUntil(usage.trial.resetsAt) });

  let banner: React.JSX.Element | null = null;
  if (usage.blocking) {
    const key = usage.trialOver ? "trialOver" : usage.blocking;
    const resetsAt = usage[usage.blocking].resetsAt;
    banner = (
      <InlineNotice tone="error" title={t(`usage.blocked.${key}.title`)}>
        {t(`usage.blocked.${key}.body`, { when: resetsAt ? upcoming(resetsAt) : "" })}
      </InlineNotice>
    );
  } else if (usage.forecast) {
    banner = (
      <InlineNotice tone="warning" title={t("usage.forecast.title")}>
        {t(`usage.forecast.${usage.forecast.window}`, {
          when: upcoming(usage.forecast.exhaustsAt),
          reset: upcoming(usage.forecast.resetsAt),
        })}
      </InlineNotice>
    );
  }

  return (
    <div className="flex max-h-[70dvh] flex-col gap-3 overflow-y-auto p-3">
      {banner}
      <WindowRow title={t("usage.session.title")} window={usage.session} caption={sessionCaption} />
      <p className="px-1 pt-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {t("usage.limitsHeading")}
      </p>
      <WindowRow title={t("usage.week.title")} window={usage.week} caption={weekCaption} />
      {usage.trial.limited || usage.trialOver ? (
        <WindowRow title={t("usage.trial.title")} window={usage.trial} caption={trialCaption} />
      ) : null}
      <p className="px-1 text-xs leading-relaxed text-muted-foreground">{t("usage.explainer")}</p>
    </div>
  );
}
