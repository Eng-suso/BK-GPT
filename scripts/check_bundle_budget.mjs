#!/usr/bin/env node
/**
 * Il peso del primo caricamento non deve tornare indietro da solo.
 *
 * Il pacchetto d'ingresso e' passato da 898 kB compressi a 113 caricando le
 * schermate a richiesta. Quel guadagno si perde con un import sbagliato in
 * cima a un file - `import { ProcessStudioPage } from ...` invece del `lazy` -
 * e non se ne accorge nessuno, perche' il prodotto continua a funzionare: e'
 * solo piu' lento ad aprirsi, per tutti, per sempre.
 *
 * Questo controllo e' deterministico: legge i file costruiti e li comprime.
 * Non dipende dall'hardware del runner, a differenza di Lighthouse, quindi puo'
 * bloccare il merge.
 *
 *     node scripts/check_bundle_budget.mjs
 *     node scripts/check_bundle_budget.mjs --update   # riscrive i budget
 */

import { gzipSync } from "node:zlib";
import { readFileSync, readdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const ASSETS = "frontend/dist/assets";
const BUDGET_FILE = "frontend/bundle-budget.json";

/** Quanto margine si concede prima di chiamarla regressione. */
const TOLERANCE = 1.1;

function gzipKb(path) {
  return Math.round((gzipSync(readFileSync(path)).length / 1024) * 10) / 10;
}

/**
 * Due numeri, non quaranta.
 *
 * Un budget per ogni pezzo costruito suonerebbe l'allarme a ogni riga spostata
 * fra un file e l'altro, e un allarme che suona sempre non lo guarda piu'
 * nessuno. I due che contano sono: quanto pesa aprire il prodotto, e quanto
 * pesa il prodotto intero.
 */
function measure() {
  let entry = 0;
  let total = 0;
  for (const file of readdirSync(ASSETS)) {
    if (!file.endsWith(".js")) continue;
    const kb = gzipKb(join(ASSETS, file));
    total += kb;
    if (/^index-[A-Za-z0-9_-]+\.js$/.test(file)) entry += kb;
  }
  return {
    "ingresso (gzip kB)": Math.round(entry * 10) / 10,
    "tutto (gzip kB)": Math.round(total * 10) / 10,
  };
}

const sizes = measure();

if (process.argv.includes("--update")) {
  writeFileSync(BUDGET_FILE, `${JSON.stringify(sizes, null, 2)}\n`, "utf8");
  console.log(`budget riscritto in ${BUDGET_FILE}:`);
  for (const [name, kb] of Object.entries(sizes)) console.log(`  ${name}: ${kb} kB`);
  process.exit(0);
}

let budget;
try {
  budget = JSON.parse(readFileSync(BUDGET_FILE, "utf8"));
} catch {
  console.error(
    `Manca ${BUDGET_FILE}. Crealo con: node scripts/check_bundle_budget.mjs --update`,
  );
  process.exit(1);
}

const problems = [];
for (const [name, allowed] of Object.entries(budget)) {
  const actual = sizes[name];
  if (actual === undefined) continue;
  if (actual > allowed * TOLERANCE) {
    problems.push(
      `${name}: ${actual}, budget ${allowed} ` +
        `(+${Math.round(((actual - allowed) / allowed) * 100)}%).`,
    );
  }
}

for (const [name, kb] of Object.entries(sizes)) {
  console.log(`${name}: ${kb} (budget ${budget[name] ?? "—"})`);
}

if (problems.length > 0) {
  console.error("\nIl pacchetto e' cresciuto oltre il budget:\n");
  for (const problem of problems) console.error(`  - ${problem}`);
  console.error(
    "\nSe la crescita e' voluta: node scripts/check_bundle_budget.mjs --update\n" +
      "Se non lo e': cerca un import in cima a un file che dovrebbe essere `lazy`\n" +
      "(frontend/src/app/screens.tsx).",
  );
  process.exit(1);
}

console.log("peso del pacchetto: dentro il budget.");
