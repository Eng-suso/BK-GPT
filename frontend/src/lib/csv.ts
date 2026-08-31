export type CsvCell = string | number | null | undefined;

const BOM = String.fromCharCode(0xfeff);

function escapeCell(value: CsvCell): string {
  const text = value == null ? "" : String(value);
  return /["\n\r,]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

/** Serialise a header row + data rows to CSV (CRLF line endings). */
export function toCsv(headers: string[], rows: CsvCell[][]): string {
  return [headers, ...rows]
    .map((row) => row.map(escapeCell).join(","))
    .join("\r\n");
}

/**
 * Prompt the browser to save `csv` as `filename`. Prepends a UTF-8 BOM so
 * Excel opens accented text correctly.
 */
export function downloadCsv(filename: string, csv: string): void {
  const blob = new Blob([BOM, csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
