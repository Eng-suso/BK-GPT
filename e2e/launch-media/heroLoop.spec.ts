/**
 * L'hero di delir.it (piano video, ottobre 2026): 20 s in loop, quattro momenti
 * da 5 s sotto le quattro frasi del sito (0/5/10/15 s).
 *
 * 1. fonti: le tre interviste entrano nel canvas e il processo si compone;
 * 2. evidenze: dal pannello delle evidenze all'attivita' che la citazione regge;
 * 3. review: la soglia di autorizzazione resta una domanda aperta, bloccante;
 * 4. proposta: As-Is e To-Be a confronto, con i valori simulati.
 *
 * Ogni momento si riprende due volte: desktop 1440x900 (16:9) e telefono
 * 390x844 (4:5, la camera segue l'azione in una finestra larga quanto lo
 * schermo). Il ritaglio del desktop non basta al telefono: una riga da 620 px
 * mostrata a 350 px scende sotto gli 11 px del piano. Italiano e inglese.
 *
 *   npx playwright test -c playwright.launch.config.ts heroLoop
 *   python3 scripts/launch_media_montage.py hero
 *
 * Velocita' 1x, cursore da 1,2 s, nessuna accelerazione al montaggio.
 */
import { expect, test, type Locator, type Page } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";

import { installCaseApi } from "./caseApi";
import { unhandled } from "./mockApi";
import { Recorder, clickOn, installCursor, moveTo } from "./recorder";
import { IDS, demoCase, type Lang } from "./vetrano";

const RAW = resolve(process.cwd(), "artifacts", "launch-media", "raw");
const OVERLAYS = resolve(process.cwd(), "artifacts", "launch-media", "overlays");
const P = `/projects/${IDS.project}/processes/${IDS.process}`;
const EASE = "cubic-bezier(.22,1,.36,1)";

const FORMATS = {
  "16x9": { use: { viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 }, suffix: "" },
  "4x5": { use: { viewport: { width: 390, height: 844 }, deviceScaleFactor: 1080 / 390, isMobile: true, hasTouch: true }, suffix: "-4x5" },
} as const;
type Format = keyof typeof FORMATS;

const UI = {
  it: {
    evidence: /Revisione delle evidenze del disegno/,
    quoted: "Citati dalle fonti",
    decide: /^Decidi$/,
    toDecide: /Da decidere/,
    details: "Dettaglio del confronto",
    showAll: "Mostra tutta la tela",
    zoomIn: /^Ingrandisci$/,
    fit: /^Centra$/,
    interview: "Intervista",
    demo: "Caso dimostrativo · valori simulati",
  },
  en: {
    evidence: /Review the drawing against the evidence/,
    quoted: "Quoted by the sources",
    decide: /^Decide$/,
    toDecide: /To decide/,
    details: "Comparison details",
    showAll: "Show entire canvas",
    zoomIn: /^Zoom in$/,
    fit: /^Fit$/,
    interview: "Interview",
    demo: "Demo case · simulated values",
  },
} as const;

test.skip(Boolean(process.env.CI) && process.env.DELIR_LAUNCH_MEDIA !== "1", "Generatore di media: in CI con DELIR_LAUNCH_MEDIA=1");

test.afterAll(() => {
  if (unhandled.size) console.warn("Richieste non coperte dal caso demo:", [...unhandled].join(", "));
});

type Rect = { x: number; y: number; width: number; height: number };

async function box(target: Locator): Promise<Rect> {
  const found = await target.boundingBox();
  if (!found) throw new Error(`nessun riquadro per ${target}`);
  return found;
}

function union(...rects: Rect[]): Rect {
  const x = Math.min(...rects.map((r) => r.x));
  const y = Math.min(...rects.map((r) => r.y));
  return { x, y, width: Math.max(...rects.map((r) => r.x + r.width)) - x, height: Math.max(...rects.map((r) => r.y + r.height)) - y };
}

/** Toglie caret e outline di focus rimasti dalla preparazione. */
async function calm(page: Page): Promise<void> {
  // Niente menu contestuale di bpmn-js sul nodo selezionato: in video e' rumore.
  await page.addStyleTag({ content: "*:focus, *:focus-visible { outline: none !important; box-shadow: none !important; } * { caret-color: transparent !important; } .djs-context-pad, .djs-popup { display: none !important; }" });
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
}

async function record(page: Page, id: string, act: (rec: Recorder) => Promise<void>): Promise<void> {
  const rec = new Recorder(page, resolve(RAW, id));
  await rec.start();
  await act(rec);
  await rec.stop();
}

const node = (page: Page, id: string) => page.locator(`.process-bpmn-canvas [data-element-id='${id}']`).first();

/**
 * Zoom del canvas con ctrl+rotella sopra un punto, finche' le etichette delle
 * attivita' non sono alte almeno `labelPx` (px CSS): bpmn-js ingrandisce
 * attorno al cursore, quindi quel punto resta fermo.
 */
async function zoomCanvas(page: Page, at: Locator, labelPx: number, delta = 60, pause = 150): Promise<void> {
  const label = () => node(page, "Task_Verifica").locator("text").first().evaluate((el) => el.getBoundingClientRect().height / Math.max(1, el.querySelectorAll("tspan").length || 1));
  const point = await box(at);
  await page.mouse.move(point.x + point.width / 2, point.y + point.height / 2);
  for (let step = 0; step < 12 && (await label()) < labelPx; step++) {
    await page.keyboard.down("Control");
    await page.mouse.wheel(0, -delta);
    await page.keyboard.up("Control");
    await page.waitForTimeout(pause);
  }
}

/** Sul telefono: la tela si rimpicciolisce finche' la pool non entra in larghezza. */
async function fitCanvas(page: Page): Promise<void> {
  const area = await box(page.locator(".process-bpmn-canvas").first());
  const pool = page.locator(".process-bpmn-canvas [data-element-id^='DeliR_Pool']").first();
  await page.mouse.move(area.x + area.width / 2, area.y + area.height / 3);
  for (let step = 0; step < 16 && (await box(pool)).width > area.width - 12; step++) {
    await page.keyboard.down("Control");
    await page.mouse.wheel(0, 60);
    await page.keyboard.up("Control");
    await page.waitForTimeout(150);
  }
  // La pool a sinistra della tela, dentro lo schermo.
  const now = await box(pool);
  await page.mouse.move(area.x + area.width / 2, area.y + area.height / 2);
  await page.mouse.wheel(now.x - area.x - 6, 0);
  await page.waitForTimeout(300);
}

async function openCanvas(page: Page, format: Format, anchor: string, labelPx: number): Promise<void> {
  await page.goto(`${P}?view=canvas`);
  await expect(node(page, "Task_Verifica")).toBeVisible();
  await page.waitForTimeout(800);
  await zoomCanvas(page, node(page, anchor), format === "16x9" ? labelPx : labelPx + 2);
  await page.mouse.move(-10, -10);
}

// --- 1. Dalle informazioni del cliente a un processo chiaro.

async function momentSources(page: Page, lang: Lang, format: Format, id: string): Promise<void> {
  const data = demoCase(lang);
  await page.goto(`${P}?view=canvas`);
  await expect(node(page, "Task_Verifica")).toBeVisible();
  await page.waitForTimeout(600);
  // Il processo intero nella tela: e' il colpo d'insieme mentre si compone.
  // Il processo intero nella tela (sul telefono fin dove lo zoom minimo arriva).
  await fitCanvas(page);
  await page.waitForTimeout(800);
  await page.mouse.move(-10, -10);
  await calm(page);
  const pool = await box(page.locator(".process-bpmn-canvas [data-element-id^='DeliR_Pool']").first());
  const viewport = page.viewportSize()!;
  await page.evaluate(({ ease, cards, pool, viewport }) => {
    const style = document.createElement("style");
    style.textContent = `
      .hero-el > .djs-outline { opacity: 0 !important; }
      .hero-el > .djs-visual { opacity: 0; transform: translateX(-12px); transition: opacity 520ms ${ease}, transform 520ms ${ease}; }
      .hero-el.in > .djs-visual { opacity: 1; transform: none; }
      body:not(.hero-playing) .hero-el > .djs-visual { transition: none; }
      .hero-card { position: fixed; z-index: 60; display: flex; align-items: center; gap: 14px; width: 330px; padding: 14px 18px;
        background: #fff; border: 1px solid #e2e8f0; border-radius: 12px; box-shadow: 0 18px 40px -18px rgba(7,17,38,.35), 0 2px 6px rgba(7,17,38,.06);
        font: 500 16px/1.3 var(--font-family-geist, system-ui), sans-serif; color: #071126;
        transition: transform 900ms ${ease}, opacity 420ms ease-out; }
      .hero-card b { flex: none; display: grid; place-items: center; width: 40px; height: 40px; border-radius: 8px; background: #004580; color: #fff; font-size: 15px; }
      .hero-card small { display: block; color: #475569; font-size: 14px; }
      .hero-card.gone { opacity: 0; }`;
    document.head.append(style);
    const elements = [...document.querySelectorAll<SVGGElement>(".process-bpmn-canvas .djs-element")]
      .map((el) => ({ el, rect: el.getBoundingClientRect() }))
      .filter(({ rect }) => rect.width > 0 || rect.height > 0);
    elements.forEach(({ el }) => el.classList.add("hero-el"));
    // Le tre interviste, una sotto l'altra al centro del processo.
    const left = Math.max(12, Math.min(viewport.width - 342, pool.x + pool.width / 2 - 165));
    const top = Math.max(80, pool.y + pool.height / 2 - 120);
    const start = document.querySelector(".process-bpmn-canvas [data-element-id='StartEvent_1']")!.getBoundingClientRect();
    const made = cards.map((card, index) => {
      const el = document.createElement("div");
      el.className = "hero-card";
      const badge = document.createElement("b");
      badge.textContent = card.initials;
      const text = document.createElement("span");
      const role = document.createElement("small");
      role.textContent = card.role;
      text.append(card.title, role);
      el.append(badge, text);
      el.style.left = `${left}px`;
      el.style.top = `${top + index * 82}px`;
      el.dataset.to = `translate(${start.left - left - 150}px, ${start.top - top - index * 82 - 20}px) scale(.12)`;
      document.body.append(el);
      return el;
    });
    const x0 = Math.min(...elements.map(({ rect }) => rect.left));
    const span = Math.max(1, Math.max(...elements.map(({ rect }) => rect.left)) - x0);
    Object.assign(window, {
      heroPlay: () => {
        document.body.classList.add("hero-playing");
        made.forEach((el, index) => setTimeout(() => { el.style.transform = el.dataset.to!; }, 1200 + index * 100));
        made.forEach((el) => setTimeout(() => el.classList.add("gone"), 1750));
        // Pool e corsie subito, poi il flusso da sinistra a destra: completo a
        // 2,7 s, cosi' il processo intero resta in quadro prima dello zoom.
        elements.forEach(({ el, rect }) => {
          const frame = rect.width > pool.width * 0.6;
          setTimeout(() => el.classList.add("in"), frame ? 1700 : 1800 + ((rect.left - x0) / span) * 900);
        });
      },
    });
  }, {
    ease: EASE,
    viewport,
    pool,
    cards: data.sources.map((source) => {
      const [title, role] = source.name.split(" · ");
      const person = title.replace(`${UI[lang].interview} `, "");
      return { title, role, initials: person.split(" ").map((part) => part[0]).join("") };
    }),
  });
  await page.waitForTimeout(400);
  const cards = page.locator(".hero-card");
  await record(page, id, async (rec) => {
    await rec.focus(union(await box(cards.first()), await box(cards.last())), 4, format === "16x9" ? 28 : 4);
    await page.evaluate(() => (window as unknown as { heroPlay: () => void }).heroPlay());
    await page.waitForTimeout(1150);
    // Il processo intero, a tutto schermo, mentre si compone.
    const poolNow = await box(page.locator(".process-bpmn-canvas [data-element-id^='DeliR_Pool']").first());
    const canvasArea = await box(page.locator(".process-bpmn-canvas").first());
    await rec.focus(format === "16x9" ? poolNow : canvasArea, 4, format === "16x9" ? 8 : 0, { overview: true });
    // Sul telefono lo zoom della tela fa parte del colpo d'insieme: parte prima.
    await page.waitForTimeout(format === "16x9" ? 1900 : 900);
    if (format === "4x5") {
      // Sul telefono la tela si ingrandisce davvero sull'inizio del processo.
      await zoomCanvas(page, node(page, "StartEvent_1"), 15, 180, 60);
    }
    const first = union(...(await Promise.all(["StartEvent_1", "Task_Compila", "Task_Invia"].map((key) => box(node(page, key))))));
    await rec.focus(first, 4, format === "16x9" ? 24 : 6);
    await page.waitForTimeout(1700);
  });
}

// --- 2. Verifica il modello, insieme alle sue fonti.

async function momentEvidence(page: Page, lang: Lang, format: Format, id: string): Promise<void> {
  await openCanvas(page, format, "Task_Verifica", 15);
  await page.getByRole("button", { name: UI[lang].evidence }).click();
  const panel = page.locator(".process-evidence-panel");
  await expect(panel).toBeVisible();
  await panel.locator("summary", { hasText: UI[lang].quoted }).click();
  const label = demoCase(lang).provenance.elements.find((item) => item.element_id === "Task_Verifica")!.label;
  const row = panel.locator("li").filter({ has: page.getByRole("button", { name: label, exact: true }) });
  await row.scrollIntoViewIfNeeded();
  await page.waitForTimeout(500);
  await calm(page);
  const button = row.getByRole("button", { name: label, exact: true });
  await record(page, id, async (rec) => {
    // Prima la citazione, poi l'attivita' che regge: una cosa per volta.
    await rec.focus(await box(row), 4, format === "16x9" ? 18 : -34);
    await page.waitForTimeout(300);
    await clickOn(page, button);
    await page.waitForTimeout(1000);
    // Sul telefono il pannello copre la tela: la camera resta sulla citazione.
    if (format === "16x9") await rec.focus(await box(node(page, "Task_Verifica")), 4, 120);
    await page.waitForTimeout(2600);
  });
}

// --- 3. Porta in review cio' che va chiarito.

async function momentReview(page: Page, lang: Lang, format: Format, id: string): Promise<void> {
  await page.goto(P);
  await page.getByRole("button", { name: UI[lang].decide }).click();
  await page.getByRole("button", { name: UI[lang].toDecide }).click();
  const question = page.getByText(demoCase(lang).review.open_questions[0].question);
  await expect(question).toBeVisible();
  const options = demoCase(lang).review.open_questions[0].options;
  const first = page.getByText(options[0].label).first();
  const second = page.getByText(options[1].label).first();
  await second.scrollIntoViewIfNeeded();
  await page.waitForTimeout(500);
  await calm(page);
  const area = union(await box(question), await box(second));
  await record(page, id, async (rec) => {
    await rec.focus(area, 4, format === "16x9" ? 40 : 12);
    await page.waitForTimeout(600);
    await moveTo(page, first);
    await page.waitForTimeout(3200);
  });
}

// --- 4. Arriva dal cliente con una proposta che puoi spiegare.

async function momentProposal(page: Page, lang: Lang, format: Format, id: string): Promise<void> {
  await page.goto(`${P}/simulation/compare?a=${IDS.asIsRun}&b=${IDS.toBeRun}`);
  const details = page.getByText(UI[lang].details, { exact: true });
  await expect(details).toBeVisible();
  // La tela piena (processo con le differenze e KPI) e il dettaglio gia' aperto.
  await page.getByRole("button", { name: UI[lang].showAll }).click().catch(() => undefined);
  await details.click();
  const rows = page.getByRole("row");
  await expect(rows.nth(4)).toBeVisible();
  // Sul telefono la tela sta sopra il pannello: si parte da li'.
  if (format === "4x5") {
    await page.locator(".sim-analytical-canvas").first().scrollIntoViewIfNeeded();
    await page.getByRole("button", { name: UI[lang].showAll }).click().catch(() => undefined);
  }
  await page.waitForTimeout(1000);
  await page.mouse.move(-10, -10);
  await calm(page);
  // Processo e KPI della tela, senza la cornice della pagina.
  const canvas = await page.evaluate(() => {
    const root = document.querySelector(".sim-analytical-canvas")!;
    const parts = [...root.querySelectorAll(".djs-container, [data-canvas-widget]")].map((el) => el.getBoundingClientRect()).filter((r) => r.width > 0);
    const x = Math.min(...parts.map((r) => r.left));
    const y = Math.min(...parts.map((r) => r.top)) - 28;
    return { x, y, width: Math.max(...parts.map((r) => r.right)) - x, height: Math.max(...parts.map((r) => r.bottom)) - y };
  });
  await page.evaluate(() => document.getElementById("launch-cursor")?.style.setProperty("display", "none"));
  await record(page, id, async (rec) => {
    await rec.focus(canvas, 4, 8, { overview: true });
    await page.waitForTimeout(1900);
    if (format === "4x5") await rows.nth(4).scrollIntoViewIfNeeded();
    // Attraversamento medio (riga 1) e costo per caso (riga 4). Sul telefono la
    // colonna delle differenze (testo piu' piccolo) resta fuori.
    const cells = (row: number) => (format === "16x9" ? rows.nth(row) : rows.nth(row).getByRole("cell").nth(2));
    const table = union(await box(rows.nth(1).getByRole("cell").first()), await box(cells(1)), await box(cells(4)));
    await rec.focus(table, 4, format === "16x9" ? 18 : -4);
    await page.waitForTimeout(3000);
  });
}

const MOMENTS = [
  ["1-fonti", momentSources],
  ["2-evidenze", momentEvidence],
  ["3-review", momentReview],
  ["4-proposta", momentProposal],
] as const;

for (const lang of ["it", "en"] as const) {
  for (const format of Object.keys(FORMATS) as Format[]) {
    test.describe(`hero ${lang} ${format}`, () => {
      test.use(FORMATS[format].use);
      test.beforeEach(async ({ page }) => {
        page.setDefaultTimeout(20_000);
        await installCaseApi(page, lang, { layout: "panel" });
        await installCursor(page);
      });
      for (const [name, moment] of MOMENTS) {
        const id = `hero-${lang}-${name}${FORMATS[format].suffix}`;
        test(id, async ({ page }) => moment(page, lang, format, id));
      }
    });
  }
}

// --- "Caso dimostrativo": la dicitura nel video, alla dimensione di ogni formato.

test("hero-overlays", async ({ page }) => {
  mkdirSync(OVERLAYS, { recursive: true });
  for (const lang of ["it", "en"] as const) {
    for (const [format, size, font] of [["16x9", [1920, 1080], 28], ["4x5", [1080, 1350], 34]] as const) {
      await page.setViewportSize({ width: size[0], height: size[1] });
      await page.setContent(`<!doctype html><html><body style="margin:0;background:transparent">
        <div style="position:fixed;right:${font}px;bottom:${font}px;padding:${font * 0.35}px ${font * 0.7}px;border-radius:999px;
          background:rgba(255,255,255,.92);border:1px solid #e2e8f0;color:#334155;font:500 ${font}px/1.2 system-ui,sans-serif">${UI[lang].demo}</div>
        </body></html>`);
      await page.screenshot({ path: resolve(OVERLAYS, `dimostrativo-${lang}-${format}.png`), omitBackground: true });
    }
  }
});
