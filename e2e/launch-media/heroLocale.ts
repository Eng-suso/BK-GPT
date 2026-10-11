/**
 * I nomi del caso demo in inglese, per il video hero della landing (che e' in
 * inglese). Solo nomi: processo, corsie, attivita', gateway, risorse, scenari,
 * fonti. Le citazioni delle interviste non passano di qui e nell'hero non si
 * leggono.
 */
const NAMES: Record<string, string> = {
  "Gestione acquisto materiali indiretti e servizi": "Indirect materials & services purchasing",
  "Acquisti indiretti e servizi": "Indirect purchasing",
  "Rileva fabbisogno durante il giro impianti": "Spot need during plant round",
  "Invia richiesta all'Ufficio Tecnico": "Send request to Engineering",
  "Invia richiesta ad Acquisti": "Send request to Purchasing",
  "Chiama fornitore direttamente": "Call supplier directly",
  "Invia riferimento ordine del fornitore": "Send supplier order reference",
  "Ricostruisci richiesta e informazioni mancanti": "Rebuild request and missing details",
  "Verifica lavorabilità della richiesta": "Check request is workable",
  "Richiedi integrazione della richiesta": "Ask for missing information",
  "Richiedi autorizzazione al responsabile": "Ask manager for approval",
  "Autorizza spesa": "Approve spend",
  "Seleziona fornitore o richiedi quotazioni": "Select supplier or request quotes",
  "Emetti ordine al fornitore": "Issue purchase order",
  "Ricevi merce in magazzino": "Receive goods",
  "Verifica merce ricevuta": "Check received goods",
  "Regolarizza ordine a posteriori": "Regularise order afterwards",
  "Gestione contabile della fattura": "Book the invoice",
  "Fabbisogno rilevato": "Need spotted",
  "Merce verificata": "Goods checked",
  "Ordine urgente registrato": "Urgent order recorded",
  "Linea ferma?": "Line stopped?",
  "Richiesta completa?": "Request complete?",
  "Serve autorizzazione?": "Approval needed?",
  "Responsabile Acquisti": "Purchasing Manager",
  "Ufficio Acquisti": "Purchasing",
  "Ufficio Tecnico": "Engineering",
  "Amministrazione": "Accounting",
  "Magazzino": "Warehouse",
  "Reparto": "Maintenance",
  "Situazione attuale": "Current process",
  "Delega giornaliera": "Daily delegate",
  "Richiesta completa + delega": "Complete request + delegate",
  "Responsabile presente a tratti": "Manager available twice a week",
  "Autorizzazione ogni giorno (delega)": "Daily approval (delegate)",
  "Richieste in coda": "Queued requests",
  "Tempo medio di attraversamento": "Average cycle time",
  "Richieste concluse": "Completed requests",
  "Costo accumulato": "Accrued cost",
  "Occupazione delle risorse": "Resource utilisation",
  "Simulazione": "Simulation",
  "responsabile-assente": "manager-twice-weekly",
  "responsabile-con-delega": "daily-delegate",
};

const FLOW_LABELS: Record<string, string> = { "Sì": "Yes", No: "No" };

const ordered = Object.entries(NAMES).sort((a, b) => b[0].length - a[0].length);

/** Sostituisce i nomi italiani dentro qualunque testo (JSON serializzato o XML). */
export function toEnglish(text: string): string {
  let out = text;
  for (const [it, en] of ordered) {
    out = out.split(it).join(en);
    // Negli attributi XML l'apostrofo puo' essere un'entita'.
    if (it.includes("'")) out = out.split(it.replace(/'/g, "&apos;")).join(en);
  }
  for (const [it, en] of Object.entries(FLOW_LABELS)) {
    // Nel JSON serializzato le virgolette dell'XML sono escapate.
    for (const quote of ['"', '\\"']) out = out.split(`name=${quote}${it}${quote}`).join(`name=${quote}${en}${quote}`);
    out = out.split(`"name":"${it}"`).join(`"name":"${en}"`);
  }
  return out;
}

/** Un corpo JSON con i nomi tradotti. */
export function englishJson<T>(body: T): T {
  return JSON.parse(toEnglish(JSON.stringify(body))) as T;
}

/** Le fonti della scheda Sources nell'hero: i quattro tipi di conoscenza del cliente. */
export const HERO_SOURCES = [
  { title: "Purchasing procedure v3.pdf", kind: "document", icon: "pdf", claims: 14 },
  { title: "Interview · F. Neri, Purchasing", kind: "interview", icon: "transcript", claims: 17 },
  { title: "Purchase requests 2026.xlsx", kind: "spreadsheet", icon: "sheet", claims: 9 },
  { title: "Kick-off meeting notes", kind: "notes", icon: "notes", claims: 6 },
];
