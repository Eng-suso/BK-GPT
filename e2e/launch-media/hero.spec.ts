/**
 * Il video hero della landing: il processo compatto (3 corsie, 5 attivita'),
 * mostrato sempre per intero, in tre momenti che si capiscono senza leggere
 * (docs/launch/hero-video.md):
 *
 * 1. i documenti del cliente entrano nel canvas e il processo si compone;
 * 2. la simulazione dell'As-Is: i casi si accumulano sull'approvazione;
 * 3. As-Is sopra, To-Be sotto: stesso flusso di richieste, uno si blocca e
 *    l'altro scorre.
 *
 *   npm run media:hero
 *
 * Niente cursore e niente frasi. Il movimento e' una funzione del tempo
 * (transizioni CSS sopra l'interfaccia vera), quindi ogni ripresa e' uguale.
 */
import { expect, test, type Page } from "@playwright/test";
import { resolve } from "node:path";

import { IDS, simulationLayoutKey } from "./demo";
import { heroSimulationLayoutSolo } from "./heroData";
import { installDemoApi, unhandled } from "./mockApi";
import { Recorder } from "./recorder";

const RAW = resolve(process.cwd(), "artifacts", "launch-media", "raw");
const P = `/projects/${IDS.project}/processes/${IDS.process}`;
const EASE = "cubic-bezier(.22,1,.36,1)";

test.skip(Boolean(process.env.CI) && process.env.DELIR_LAUNCH_MEDIA !== "1", "Generatore di media: in CI con DELIR_LAUNCH_MEDIA=1");
// 1440x810 a densita' 4/3: fotogrammi 1920x1080 con l'interfaccia un terzo piu' grande.
test.use({ viewport: { width: 1440, height: 810 }, deviceScaleFactor: 4 / 3 });

test.beforeEach(async ({ page }) => {
  page.setDefaultTimeout(30_000);
  await installDemoApi(page, "en", { hero: true });
});

test.afterAll(() => {
  if (unhandled.size) console.warn("Richieste non coperte dal caso demo:", [...unhandled].join(", "));
});

async function record(page: Page, id: string, act: (rec: Recorder) => Promise<void>): Promise<void> {
  const rec = new Recorder(page, resolve(RAW, id));
  await rec.start();
  await act(rec);
  await rec.stop();
}

/** Toglie caret e outline di focus rimasti dalla preparazione. */
async function calm(page: Page): Promise<void> {
  await page.addStyleTag({ content: "*:focus, *:focus-visible { outline: none !important; box-shadow: none !important; } * { caret-color: transparent !important; }" });
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
}

/** Il rettangolo che contiene tutto il processo (pool compreso), in px CSS. */
async function processBox(page: Page, scope = "body"): Promise<{ x: number; y: number; width: number; height: number }> {
  return page.evaluate((root) => {
    const boxes = [...document.querySelectorAll(`${root} .djs-container .djs-element`)]
      .map((el) => el.getBoundingClientRect())
      .filter((box) => box.width > 0 && box.height > 0);
    const x = Math.min(...boxes.map((b) => b.left));
    const y = Math.min(...boxes.map((b) => b.top));
    return { x, y, width: Math.max(...boxes.map((b) => b.right)) - x, height: Math.max(...boxes.map((b) => b.bottom)) - y };
  }, scope);
}

// --- 1. Dai documenti al processo.

test("hero-build", async ({ page }) => {
  await page.goto(`${P}?view=canvas`);
  await expect(page.locator("[data-element-id='approve_spend']").first()).toBeVisible();
  await calm(page);
  await page.waitForTimeout(800);
  const box = await processBox(page);
  await page.evaluate(({ ease, box }) => {
    const style = document.createElement("style");
    style.textContent = `
      .hero-el > .djs-outline { opacity: 0 !important; }
      .hero-el > .djs-visual { opacity: 0; transform: translateX(-10px); transition: opacity 500ms ${ease}, transform 500ms ${ease}; }
      .hero-el.in > .djs-visual { opacity: 1; transform: none; }
      .hero-file { position: fixed; z-index: 50; display: flex; align-items: center; gap: 12px; padding: 12px 16px; width: 270px;
        background: #fff; border: 1px solid #dfe1e5; border-radius: 14px; box-shadow: 0 18px 40px -18px rgba(15,23,42,.35), 0 2px 6px rgba(15,23,42,.06);
        font: 550 15px/1.25 "Geist Variable", Geist, system-ui, sans-serif; color: #0f172a;
        transition: transform 1000ms ${ease}, opacity 450ms ease-out; }
      .hero-file b { flex: none; display: grid; place-items: center; width: 38px; height: 44px; border-radius: 7px; font-size: 10px; font-weight: 700; letter-spacing: .04em; color: #fff; }
      .hero-file.gone { opacity: 0; }`;
    document.head.append(style);
    const elements = [...document.querySelectorAll<SVGGElement>(".djs-container .djs-element")]
      .map((el) => ({ el, rect: el.getBoundingClientRect() }))
      .filter(({ rect }) => rect.width > 0 || rect.height > 0);
    const frame = elements.filter(({ rect }) => rect.width > box.width * 0.6);
    const flow = elements.filter(({ rect }) => rect.width <= box.width * 0.6);
    [...frame, ...flow].forEach(({ el }) => el.classList.add("hero-el"));
    // I quattro documenti del cliente, sparsi intorno al processo.
    const files = [
      { tag: "PDF", color: "#dc2626", name: "Purchasing procedure.pdf", dx: -0.42, dy: -0.38, rot: -7 },
      { tag: "TXT", color: "#7c3aed", name: "Interview transcript", dx: 0.42, dy: -0.34, rot: 6 },
      { tag: "XLS", color: "#15803d", name: "Purchase requests.xlsx", dx: -0.38, dy: 0.4, rot: 5 },
      { tag: "DOC", color: "#d97706", name: "Meeting notes", dx: 0.4, dy: 0.38, rot: -5 },
    ];
    const cx = box.x + box.width / 2;
    const cy = box.y + box.height / 2;
    const cards = files.map((file) => {
      const card = document.createElement("div");
      card.className = "hero-file";
      const tag = document.createElement("b");
      tag.style.background = file.color;
      tag.textContent = file.tag;
      const name = document.createElement("span");
      name.textContent = file.name;
      card.append(tag, name);
      document.body.append(card);
      const left = cx + file.dx * box.width - 135;
      const top = cy + file.dy * box.height - 34;
      card.style.left = `${left}px`;
      card.style.top = `${top}px`;
      card.style.transform = `rotate(${file.rot}deg)`;
      card.dataset.to = `translate(${cx - 135 - left}px, ${cy - 34 - top}px) scale(.55) rotate(0deg)`;
      return card;
    });
    const left = Math.min(...flow.map(({ rect }) => rect.left));
    const right = Math.max(...flow.map(({ rect }) => rect.left));
    Object.assign(window, {
      heroPlay: () => {
        cards.forEach((card, index) => setTimeout(() => { card.style.transform = card.dataset.to!; }, 500 + index * 90));
        cards.forEach((card) => setTimeout(() => card.classList.add("gone"), 1350));
        setTimeout(() => frame.forEach(({ el }) => el.classList.add("in")), 1450);
        flow.forEach(({ el, rect }) => setTimeout(() => el.classList.add("in"), 1650 + ((rect.left - left) / Math.max(1, right - left)) * 1300));
      },
    });
  }, { ease: EASE, box });
  // Il primo fotogramma del screencast deve gia' avere il processo nascosto.
  await page.waitForTimeout(500);
  await record(page, "hero-build", async (rec) => {
    // Il processo intero, grande: niente tagli.
    await rec.focus(box, 1.6, 30);
    await page.evaluate(() => (window as unknown as { heroPlay: () => void }).heroPlay());
    await page.waitForTimeout(4600);
  });
});

// --- 2 e 3. La simulazione: As-Is e To-Be, stesso flusso di richieste.

async function replay(page: Page, run: number, id: string): Promise<void> {
  await page.goto(`${P}/simulation/replay/${run}`);
  await expect(page.getByRole("button", { name: "Play", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Show entire canvas" }).click();
  // La seconda velocita' piu' rapida: i casi si vedono passare uno per uno.
  await page.getByRole("combobox", { name: /Speed/ }).click();
  const options = page.getByRole("option");
  await options.nth((await options.count()) - 2).click();
  await calm(page);
  await page.waitForTimeout(1000);
  await expect(page.getByRole("heading", { name: "Accrued cost", level: 4 })).toBeVisible();
  // Processo e KPI insieme: la tela intera, niente tagliato.
  const process = await processBox(page);
  const kpis = await page.evaluate(() => ["Average cycle time", "Queued cases", "Throughput", "Accrued cost"].map((title) => {
    const el = [...document.querySelectorAll("h4")].find((node) => node.textContent?.trim() === title)!;
    let card = el as HTMLElement;
    while (card.parentElement && card.getBoundingClientRect().height < 120) card = card.parentElement;
    const r = card.getBoundingClientRect();
    return { x: r.left, y: r.top, right: r.right, bottom: r.bottom };
  }));
  const x = Math.min(process.x, ...kpis.map((k) => k.x));
  const y = Math.min(process.y, ...kpis.map((k) => k.y));
  const box = { x, y, width: Math.max(process.x + process.width, ...kpis.map((k) => k.right)) - x, height: Math.max(process.y + process.height, ...kpis.map((k) => k.bottom)) - y };
  await record(page, id, async (rec) => {
    await rec.focus(box, 2.2, 24);
    await page.getByRole("button", { name: "Play", exact: true }).click();
    await calm(page);
    await page.waitForTimeout(11_000);
  });
}

test("hero-replay-asis", async ({ page }) => replay(page, IDS.asIsRun, "hero-replay-asis"));
// L'As-Is da solo: i grafici sotto il processo, cosi' la tela riempie il 16:9.
test("hero-replay-asis-solo", async ({ page }) => {
  await page.addInitScript(({ key, layout }) => window.localStorage.setItem(key, layout), { key: simulationLayoutKey, layout: JSON.stringify(heroSimulationLayoutSolo) });
  await replay(page, IDS.asIsRun, "hero-replay-asis-solo");
});
test("hero-replay-tobe", async ({ page }) => replay(page, IDS.toBeRun, "hero-replay-tobe"));

// --- Etichette dello schermo diviso e disclaimer (PNG trasparenti).

test("hero-overlays", async ({ page }) => {
  const dir = resolve(process.cwd(), "artifacts", "launch-media", "overlays");
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/home");
  const font = (await page.evaluate(() => getComputedStyle(document.body).fontFamily)).replace(/"/g, "'");
  const render = async (name: string, body: string) => {
    await page.setContent(`<!doctype html><html><body style="margin:0;background:transparent;font-family:${font}">${body}</body></html>`);
    await page.screenshot({ path: resolve(dir, `${name}.png`), omitBackground: true });
  };
  const pill = (text: string, top: number, color: string) => `<div style="position:fixed;left:28px;top:${top}px;display:inline-flex;align-items:center;gap:12px;padding:10px 20px 10px 14px;border-radius:999px;background:rgba(15,23,42,.9);color:#fff;font-size:30px;font-weight:650;letter-spacing:-0.01em">
    <span style="width:14px;height:14px;border-radius:50%;background:${color}"></span>${text}</div>`;
  await render("label-asis", pill("As-Is", 24, "#f97316"));
  await render("label-tobe", pill("To-Be", 564, "#22c55e"));
  await render("label-asis-solo", pill("As-Is", 24, "#f97316"));
  await render("disclaimer-hero", `<div style="position:fixed;right:18px;bottom:14px;font-size:17px;color:#475569;background:rgba(255,255,255,.92);border:1px solid #e2e8f0;border-radius:999px;padding:6px 14px">Demo data · simulated example</div>`);
});
