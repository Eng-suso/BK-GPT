import { useTranslation } from "react-i18next";
import { Loader2 } from "lucide-react";

import { InlineNotice } from "@/components/feedback/InlineNotice";
import { Button } from "@/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/ui/popover";
import { cn } from "@/lib/utils";
import {
  headlineShare,
  usageTone,
  useUsageQuery,
  type Usage,
  type UsageTone,
  type UsageWindow,
  type UsageWindowName,
} from "./api";

const TONE_COLOR: Record<UsageTone, string> = {
  normal: "var(--primary)",
  warning: "var(--color-status-warning)",
  danger: "var(--color-status-danger)",
};

/** Percentuale intera per le persone: 0,4% si legge "1%", non "0%" (qualcosa e' stato usato). */
function percent(share: number): number {
  if (share <= 0) return 0;
  return Math.max(1, Math.min(100, Math.round(share * 100)));
}

function sameDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

/** "20:20" oggi, "domani 01:00", altrimenti "mar 01:00". Nel fuso del consulente. */
function formatMoment(iso: string, locale: string, t: (key: string, options?: Record<string, unknown>) => string): string {
  const when = new Date(iso);
  const now = new Date();
  const time = new Intl.DateTimeFormat(locale, { hour: "2-digit", minute: "2-digit" }).format(when);
  if (sameDay(when, now)) return t("usage.when.today", { time });
  const tomorrow = new Date(now);
  tomorrow.setDate(now.getDate() + 1);
  if (sameDay(when, tomorrow)) return t("usage.when.tomorrow", { time });
  const day = new Intl.DateTimeFormat(locale, { weekday: "short" }).format(when);
  return t("usage.when.weekday", { day, time });
}

function formatDay(iso: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, { day: "numeric", month: "short" }).format(new Date(iso));
}

function daysLeft(iso: string): number {
  return Math.max(0, Math.ceil((new Date(iso).getTime() - Date.now()) / 86_400_000));
}

/**
 * L'anello della barra: la quota della finestra piu' vicina al limite.
 *
 * Un numero dentro un cerchio che si riempie: si legge a colpo d'occhio senza
 * aprire niente, e cambia colore prima che il limite arrivi, non dopo.
 */
export function UsageRing({ share, tone, size = 28 }: { share: number; tone: UsageTone; size?: number }): React.JSX.Element {
  const stroke = 3;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const value = percent(share);
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true" className="block">
      <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="var(--border)" strokeWidth={stroke} />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke={TONE_COLOR[tone]}
        strokeWidth={stroke}
        strokeLinecap="round"
        strokeDasharray={circumference}
        strokeDashoffset={circumference * (1 - Math.min(1, share))}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
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

function UsageBar({ share, tone, label }: { share: number; tone: UsageTone; label: string }): React.JSX.Element {
  const value = percent(share);
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={value}
      className="h-2 w-full overflow-hidden rounded-full bg-muted"
    >
      <div
        className="h-full rounded-full transition-[width] duration-500 motion-reduce:transition-none"
        style={{ width: `${value}%`, background: TONE_COLOR[tone] }}
      />
    </div>
  );
}

function WindowRow({
  title,
  window,
  caption,
}: {
  title: string;
  window: UsageWindow;
  caption: string;
}): React.JSX.Element {
  const { t } = useTranslation("common");
  const share = window.exhausted ? 1 : window.usedShare;
  const tone = window.exhausted ? "danger" : usageTone(share);
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-border bg-card px-3 py-3">
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-body-sm font-semibold text-foreground">{title}</p>
        <p className="shrink-0 text-xs tabular-nums text-muted-foreground">
          {t("usage.used", { percent: percent(share) })}
        </p>
      </div>
      <UsageBar share={share} tone={tone} label={title} />
      <p className="text-xs text-muted-foreground">{caption}</p>
    </div>
  );
}

function Banner({ usage, locale }: { usage: Usage; locale: string }): React.JSX.Element | null {
  const { t } = useTranslation("common");
  if (usage.blocking) {
    const window = usage[usage.blocking];
    const key = usage.trial.over ? "trialOver" : usage.blocking;
    return (
      <InlineNotice tone="error" title={t(`usage.blocked.${key}.title`)}>
        {t(`usage.blocked.${key}.body`, {
          when: window.resetsAt ? formatMoment(window.resetsAt, locale, t) : "",
        })}
      </InlineNotice>
    );
  }
  if (usage.forecast) {
    return (
      <InlineNotice tone="warning" title={t("usage.forecast.title")}>
        {t(`usage.forecast.${usage.forecast.window}`, {
          when: formatMoment(usage.forecast.exhaustsAt, locale, t),
          reset: formatMoment(usage.forecast.resetsAt, locale, t),
        })}
      </InlineNotice>
    );
  }
  return null;
}

function captionFor(name: UsageWindowName, usage: Usage, locale: string, t: (key: string, options?: Record<string, unknown>) => string): string {
  const window = usage[name];
  if (name === "session") {
    return window.resetsAt
      ? t("usage.session.resets", { when: formatMoment(window.resetsAt, locale, t) })
      : t("usage.session.notStarted", { count: usage.sessionHours });
  }
  if (name === "week") {
    return window.resetsAt ? t("usage.week.resets", { when: formatMoment(window.resetsAt, locale, t) }) : "";
  }
  if (usage.trial.over || !window.resetsAt) return t("usage.trial.over");
  return t("usage.trial.ends", { day: formatDay(window.resetsAt, locale), count: daysLeft(window.resetsAt) });
}

/**
 * Il contatore d'uso della prova: anello nella barra, dettaglio nel pannello.
 *
 * Il consulente deve sapere quanto ha usato, quanto gli resta e quando si
 * ripristina, prima di trovarsi fermo. Con i limiti spenti l'anello non c'e':
 * un contatore che non conta niente sarebbe solo rumore.
 */
export function UsageMenu(): React.JSX.Element | null {
  const { t, i18n } = useTranslation("common");
  const usage = useUsageQuery();
  const locale = i18n.language || "it";

  if (!usage.data?.enabled) return null;
  const data = usage.data;
  const share = headlineShare(data);
  const tone = data.blocking ? "danger" : usageTone(share);

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={t("usage.label", { percent: percent(share) })}
          className="ui-chrome-control"
        >
          <UsageRing share={share} tone={tone} />
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

        <div className="flex max-h-[70dvh] flex-col gap-3 overflow-y-auto p-3">
          <Banner usage={data} locale={locale} />

          <WindowRow title={t("usage.session.title")} window={data.session} caption={captionFor("session", data, locale, t)} />

          <p className="px-1 pt-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {t("usage.limitsHeading")}
          </p>
          <WindowRow title={t("usage.week.title")} window={data.week} caption={captionFor("week", data, locale, t)} />
          {data.trial.limited || data.trial.over ? (
            <WindowRow
              title={t("usage.trial.title")}
              window={data.trial.over ? { ...data.trial, exhausted: true } : data.trial}
              caption={captionFor("trial", data, locale, t)}
            />
          ) : null}

          <p className={cn("px-1 text-xs leading-relaxed text-muted-foreground")}>{t("usage.explainer")}</p>
        </div>
      </PopoverContent>
    </Popover>
  );
}
