/**
 * Le date che il consulente legge.
 *
 * Il backend le conserva in ISO perche' e' un formato che si ordina e si
 * confronta; nella pagina quel formato non lo legge nessuno. La conversione
 * sta qui, in un punto solo: era gia' duplicata fra Archivio e dettaglio
 * progetto, e ogni copia avrebbe scelto le proprie abbreviazioni.
 */

/**
 * Formatta una data ISO nella lingua dell'interfaccia.
 *
 * @param iso - Data in ISO (`YYYY-MM-DD` o timestamp completo)
 * @param locale - Lingua attiva; vuota ricade sull'italiano
 * @returns La data leggibile, o la stringa originale se non e' una data
 */
export function formatDate(iso: string, locale: string): string {
  const ms = Date.parse(iso);
  if (Number.isNaN(ms)) return iso;
  return new Intl.DateTimeFormat(locale || "it", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(ms);
}

/**
 * La finestra di un incarico, con una sola data quando l'altra manca.
 *
 * @param start - Data di inizio in ISO, o `null`
 * @param end - Data di fine in ISO, o `null`
 * @param locale - Lingua attiva
 * @returns `"01 set 2026 → 15 dic 2026"`, un solo estremo con la sua freccia,
 *   o stringa vuota quando non c'e' nessuna data: un periodo dichiarato a meta'
 *   e' comunque un'informazione, due trattini no.
 */
export function formatDateRange(
  start: string | null,
  end: string | null,
  locale: string,
): string {
  if (start && end) return `${formatDate(start, locale)} → ${formatDate(end, locale)}`;
  if (start) return `${formatDate(start, locale)} →`;
  if (end) return `→ ${formatDate(end, locale)}`;
  return "";
}

export const DAY_MS = 86_400_000;

function sameDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

/**
 * Un momento vicino nel futuro, come lo dice una persona: l'ora se e' oggi,
 * "domani" se e' domani, altrimenti il giorno della settimana.
 *
 * Le parole vengono da chi chiama (i18n): qui si decide solo quale forma usare.
 *
 * @param iso - L'istante in ISO
 * @param locale - Lingua attiva
 * @param words - Le tre forme, con `{time}` e `{day}` gia' formattati
 * @returns Per esempio "alle 20:20", "domani alle 01:00", "mar alle 01:00"
 */
export function formatUpcoming(
  iso: string,
  locale: string,
  words: { today: (time: string) => string; tomorrow: (time: string) => string; weekday: (day: string, time: string) => string },
  now: Date = new Date(),
): string {
  const when = new Date(iso);
  const time = new Intl.DateTimeFormat(locale || "it", { hour: "2-digit", minute: "2-digit" }).format(when);
  if (sameDay(when, now)) return words.today(time);
  if (sameDay(when, new Date(now.getTime() + DAY_MS))) return words.tomorrow(time);
  const day = new Intl.DateTimeFormat(locale || "it", { weekday: "short" }).format(when);
  return words.weekday(day, time);
}

/** Giorno e mese corti, senza anno: "10 dic". */
export function formatDayMonth(iso: string, locale: string): string {
  return new Intl.DateTimeFormat(locale || "it", { day: "numeric", month: "short" }).format(new Date(iso));
}

/** Quanti giorni mancano a un istante, arrotondati per eccesso, mai negativi. */
export function daysUntil(iso: string, now: Date = new Date()): number {
  return Math.max(0, Math.ceil((new Date(iso).getTime() - now.getTime()) / DAY_MS));
}

/**
 * Una durata come la dice una persona: "2 h 10 min", "45 min", "6 h".
 *
 * Le unita' le scrive `Intl`, nella lingua dell'interfaccia: niente sigle
 * scritte a mano da tradurre.
 */
export function formatDuration(seconds: number, locale: string): string {
  const minutes = Math.round(Math.max(0, seconds) / 60);
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  const unit = (value: number, which: "hour" | "minute") =>
    new Intl.NumberFormat(locale || "it", { style: "unit", unit: which, unitDisplay: "short" }).format(value);
  if (hours === 0) return unit(rest, "minute");
  if (rest === 0) return unit(hours, "hour");
  return `${unit(hours, "hour")} ${unit(rest, "minute")}`;
}
