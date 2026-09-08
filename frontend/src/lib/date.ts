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
