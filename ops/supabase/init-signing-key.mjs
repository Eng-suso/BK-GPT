// Genera la chiave ES256 che firma i JWT del Supabase locale, se manca.
// La chiave privata resta in ops/supabase/signing_keys.json (ignorato da git):
// ogni macchina ha la sua. Il backend legge solo la parte pubblica (JWKS).
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const keys = path.join(here, "signing_keys.json");

const current = existsSync(keys) ? JSON.parse(readFileSync(keys, "utf8") || "[]") : [];
if (Array.isArray(current) && current.some((key) => key.alg === "ES256" && key.d)) {
  console.log("signing_keys.json presente: nessuna modifica");
  process.exit(0);
}
// La CLI aggiunge al file indicato in config.jsonc: deve esistere ed essere JSON.
writeFileSync(keys, "[]");
execFileSync("npx", ["supabase", "gen", "signing-key", "--algorithm", "ES256", "--append", "--workdir", path.dirname(here)], {
  stdio: ["ignore", "ignore", "inherit"],
  shell: process.platform === "win32",
});
const generated = JSON.parse(readFileSync(keys, "utf8"));
if (!generated.some((key) => key.alg === "ES256" && key.d)) {
  console.error("generazione della chiave ES256 fallita");
  process.exit(1);
}
console.log("creato signing_keys.json; valore non mostrato");
