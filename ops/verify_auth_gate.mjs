// E2E browser del cancello di accesso di STAGING o PROD-SIM. Non stampa segreti.
//
// Dal root del repository, con lo stack scelto acceso:
//   node ops/verify_auth_gate.mjs staging [cartella-screenshot]
//
// Verifica: form bloccato senza credenziali; token e tenant dell'altro stack
// rifiutati; credenziali proprie che aprono il workspace senza 401/403;
// sessione conservata al reload e assente in un nuovo contesto; token mai in
// localStorage, negli URL o nei bundle JS serviti.
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const target = process.argv[2];
const shots = process.argv[3];
if (!["staging", "prod-sim"].includes(target)) {
  console.error("uso: node ops/verify_auth_gate.mjs staging|prod-sim [cartella-screenshot]");
  process.exit(2);
}
const other = target === "staging" ? "prod-sim" : "staging";
const ops = path.dirname(fileURLToPath(import.meta.url));

function readEnv(name) {
  return Object.fromEntries(
    readFileSync(path.join(ops, name), "utf8")
      .split(/\r?\n/)
      .filter((line) => line.includes("=") && !line.trim().startsWith("#"))
      .map((line) => [line.slice(0, line.indexOf("=")).trim(), line.slice(line.indexOf("=") + 1).trim()]),
  );
}

const own = readEnv(`.env.${target}`);
const foreign = readEnv(`.env.${other}`);
const base = `http://127.0.0.1:${own.APP_PORT}/`;
const secrets = [own.DELIR_API_TOKEN, foreign.DELIR_API_TOKEN];
const results = [];
const check = (name, ok) => results.push([name, Boolean(ok)]);

const browser = await chromium.launch();
try {
  const page = await (await browser.newContext()).newPage();
  const urls = [];
  const statuses = [];
  page.on("request", (request) => urls.push(request.url()));
  page.on("response", (response) => {
    if (response.url().includes("/v1/")) statuses.push(response.status());
  });

  const tenant = page.locator("#local-auth-tenant");
  const token = page.locator("#local-auth-token");
  const submit = async (tenantId, apiToken) => {
    await tenant.fill(tenantId);
    await token.fill(apiToken);
    await page.locator("form button[type=submit]").click();
  };

  await page.goto(base);
  await token.waitFor({ timeout: 30000 });
  check("senza credenziali: form di accesso", true);

  await submit(own.DELIR_DEFAULT_TENANT_ID, foreign.DELIR_API_TOKEN);
  await page.locator("[role=alert]").waitFor({ timeout: 15000 });
  check(`token di ${other}: rifiutato, resta bloccato`, await token.isVisible());

  await submit(foreign.DELIR_DEFAULT_TENANT_ID, own.DELIR_API_TOKEN);
  await page.locator("[role=alert]").waitFor({ timeout: 15000 });
  check(`tenant di ${other}: rifiutato, resta bloccato`, await token.isVisible());

  statuses.length = 0;
  await submit(own.DELIR_DEFAULT_TENANT_ID, own.DELIR_API_TOKEN);
  await token.waitFor({ state: "detached", timeout: 15000 });
  await page.waitForLoadState("networkidle").catch(() => {});
  check("credenziali proprie: workspace aperto", (await token.count()) === 0);
  check("nessun 401/403 dopo l'accesso", statuses.length > 0 && !statuses.some((s) => s === 401 || s === 403));
  if (shots) await page.screenshot({ path: path.join(shots, `${target}-workspace.png`) });

  await page.reload();
  await page.waitForLoadState("networkidle").catch(() => {});
  check("reload: sessione conservata", (await page.locator("#local-auth-token").count()) === 0);

  const storage = await page.evaluate(() => JSON.stringify({ ...localStorage }));
  check("token assente da localStorage", !secrets.some((secret) => storage.includes(secret)));
  check(
    "token assente dagli URL",
    !urls.some((url) => secrets.some((secret) => url.includes(secret) || url.includes(encodeURIComponent(secret)))),
  );

  const bundles = [...new Set(urls.filter((url) => url.startsWith(base) && url.endsWith(".js")))];
  let leaked = false;
  for (const bundle of bundles) {
    const body = await (await fetch(bundle)).text();
    if (secrets.some((secret) => body.includes(secret))) leaked = true;
  }
  check(`token assente dai ${bundles.length} bundle JS`, bundles.length > 0 && !leaked);

  const fresh = await (await browser.newContext()).newPage();
  await fresh.goto(base);
  await fresh.locator("#local-auth-token").waitFor({ timeout: 30000 });
  check("nuova sessione browser: bloccata", true);
} finally {
  await browser.close();
}

console.log(`== E2E cancello di accesso ${target} (${base})`);
for (const [name, ok] of results) console.log(`${ok ? "PASS" : "FAIL"}  ${name}`);
console.log(`TOTALE: ${results.filter(([, ok]) => ok).length}/${results.length}`);
process.exit(results.every(([, ok]) => ok) ? 0 : 1);
