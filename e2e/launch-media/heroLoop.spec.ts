/**
 * L'hero di delir.it (piano video, ottobre 2026): 20 s in loop, quattro momenti
 * da 5 s sotto le quattro frasi del sito (0/5/10/15 s).
 *
 * 1. editing: interviste, Word, Excel e l'export del gestionale entrano nel
 *    canvas e il processo intero si compone;
 * 2. informazioni: la citazione si accende e una linea blu la porta
 *    all'attivita' che regge;
 * 3. As-Is: il replay con processo e 4 KPI, poi la heatmap dell'intera
 *    esecuzione accende il collo di bottiglia in rosso;
 * 4. To-Be: il confronto con l'As-Is, lo stesso punto diventa verde, -87% di
 *    attraversamento e -43% di costo;
 * 5. invio: il processo va al cliente con il link privato.
 *
 * Revisioni di Sohayb del 14 ottobre: si vede sempre il desktop, una
 * targhetta blu per momento, nessuno zoom sull'inizio del processo, solo
 * 16:9 (la versione da telefono non si capiva). Italiano e inglese.
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
import { EASE, OVERLAYS, box, calm, record, union, type Rect } from "./kit";
import { clickOn, installCursor, moveTo, pause as pauseFor } from "./recorder";
import { IDS, demoCase, type Lang } from "./vetrano";

const P = `/projects/${IDS.project}/processes/${IDS.process}`;

// Una sola ripresa, desktop 1440x900 a densita' 2 (progetto "desktop" di
// playwright.launch.config.ts).
test.use({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });

const UI = {
  it: {
    evidence: /Revisione delle evidenze del disegno/,
    quoted: "Citati dalle fonti",
    panelTitle: "Evidenze del disegno",
    decide: /^Decidi$/,
    toDecide: /Da decidere/,
    details: "Dettaglio del confronto",
    showAll: "Mostra tutta la tela",
    play: "Riproduci",
    compare: "Confronto",
    heatmap: "Heatmap",
    wholeRun: /Applica heatmap/,
    speed: "Velocità",
    send: /Invia al cliente/,
    sent: "Ho inviato il link",
    zoomIn: /^Ingrandisci$/,
    fit: /^Centra$/,
    interview: "Intervista",
    demo: "Caso dimostrativo · valori simulati",
  },
  en: {
    evidence: /Review the drawing against the evidence/,
    quoted: "Quoted by the sources",
    panelTitle: "Drawing evidence",
    decide: /^Decide$/,
    toDecide: /To decide/,
    details: "Comparison details",
    showAll: "Show entire canvas",
    play: "Play",
    compare: "Compare",
    heatmap: "Heatmap",
    wholeRun: /Apply whole-run heatmap/,
    speed: "Speed",
    send: /Send to client/,
    sent: "I sent the link",
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
    await pauseFor(page, pause);
  }
}

/** La tela si rimpicciolisce finche' la pool non entra in larghezza. */
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

async function openCanvas(page: Page, anchor: string, labelPx: number): Promise<void> {
  await page.goto(`${P}?view=canvas`);
  await expect(node(page, "Task_Verifica")).toBeVisible();
  await page.waitForTimeout(800);
  await zoomCanvas(page, node(page, anchor), labelPx);
  await page.mouse.move(-10, -10);
}

// --- 1. Dalle informazioni del cliente a un processo chiaro.

/** Le fonti che il consulente porta: interviste e i file del cliente. */
const FILES = {
  it: [
    { kind: "word", title: "Procedura acquisti.docx", detail: "Documento Word · 12 pagine" },
    { kind: "excel", title: "Richieste 2026.xlsx", detail: "Foglio Excel · 418 righe" },
    { kind: "erp", title: "Export dal gestionale", detail: "Ordini e fornitori · CSV" },
  ],
  en: [
    { kind: "word", title: "Purchasing procedure.docx", detail: "Word document · 12 pages" },
    { kind: "excel", title: "Requests 2026.xlsx", detail: "Excel sheet · 418 rows" },
    { kind: "erp", title: "ERP export", detail: "Orders and suppliers · CSV" },
  ],
} as const;

async function momentSources(page: Page, lang: Lang, id: string): Promise<void> {
  const data = demoCase(lang);
  await page.goto(`${P}?view=canvas`);
  await expect(node(page, "Task_Verifica")).toBeVisible();
  await page.waitForTimeout(600);
  // Il processo intero nella tela: e' il colpo d'insieme mentre si compone.
  await fitCanvas(page);
  await page.waitForTimeout(800);
  await page.mouse.move(-10, -10);
  await calm(page);
  const pool = await box(page.locator(".process-bpmn-canvas [data-element-id^='DeliR_Pool']").first());
  const interviews = data.sources.map((source) => {
    const [title, role] = source.name.split(" · ");
    const person = title.replace(`${UI[lang].interview} `, "");
    return { kind: "interview", badge: person.split(" ").map((part) => part[0]).join(""), title, detail: role };
  });
  await page.evaluate(({ ease, cards, pool }) => {
    const style = document.createElement("style");
    style.textContent = `
      .hero-el > .djs-outline { opacity: 0 !important; }
      .hero-el > .djs-visual { opacity: 0; transform: translateX(-12px); transition: opacity 520ms ${ease}, transform 520ms ${ease}; }
      .hero-el.in > .djs-visual { opacity: 1; transform: none; }
      body:not(.hero-playing) .hero-el > .djs-visual { transition: none; }
      .hero-card { position: fixed; z-index: 60; display: flex; align-items: center; gap: 14px; width: 340px; padding: 14px 18px;
        background: #fff; border: 1px solid #e2e8f0; border-radius: 12px; box-shadow: 0 18px 40px -18px rgba(7,17,38,.35), 0 2px 6px rgba(7,17,38,.06);
        font: 600 18px/1.3 var(--font-family-geist, system-ui), sans-serif; color: #071126;
        transition: transform 900ms ${ease}, opacity 420ms ease-out; }
      .hero-card i { flex: none; display: grid; place-items: center; width: 44px; height: 44px; border-radius: 9px; color: #fff;
        font: 700 17px/1 var(--font-family-geist, system-ui), sans-serif; font-style: normal; }
      .hero-card i.interview { background: #004580; }
      .hero-card i.word { background: #185abd; }
      .hero-card i.excel { background: #107c41; }
      .hero-card i.erp { background: #475569; }
      .hero-card small { display: block; color: #475569; font-size: 15px; font-weight: 500; }
      .hero-card.gone { opacity: 0; }`;
    document.head.append(style);
    const elements = [...document.querySelectorAll<SVGGElement>(".process-bpmn-canvas .djs-element")]
      .map((el) => ({ el, rect: el.getBoundingClientRect() }))
      .filter(({ rect }) => rect.width > 0 || rect.height > 0);
    elements.forEach(({ el }) => el.classList.add("hero-el"));
    // Una colonna al centro del processo: prima le interviste, poi i file.
    const W = 340, ROW = 78;
    const left = pool.x + pool.width / 2 - W / 2;
    const top = Math.max(90, pool.y + pool.height / 2 - (cards.length * ROW) / 2);
    const start = document.querySelector(".process-bpmn-canvas [data-element-id='StartEvent_1']")!.getBoundingClientRect();
    const db = '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2"><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/></svg>';
    const made = cards.map((card, index) => {
      const el = document.createElement("div");
      el.className = "hero-card";
      const icon = document.createElement("i");
      icon.className = card.kind;
      if (card.kind === "erp") icon.innerHTML = db;
      else icon.textContent = card.kind === "word" ? "W" : card.kind === "excel" ? "X" : card.badge;
      const text = document.createElement("span");
      const detail = document.createElement("small");
      detail.textContent = card.detail;
      text.append(card.title, detail);
      el.append(icon, text);
      const x = left;
      const y = top + index * ROW;
      el.style.left = `${x}px`;
      el.style.top = `${y}px`;
      el.dataset.to = `translate(${start.left - x - 150}px, ${start.top - y - 20}px) scale(.12)`;
      document.body.append(el);
      return el;
    });
    const x0 = Math.min(...elements.map(({ rect }) => rect.left));
    const span = Math.max(1, Math.max(...elements.map(({ rect }) => rect.left)) - x0);
    Object.assign(window, {
      heroPlay: () => {
        document.body.classList.add("hero-playing");
        made.forEach((el, index) => setTimeout(() => { el.style.transform = el.dataset.to!; }, 1150 + index * 70));
        made.forEach((el) => setTimeout(() => el.classList.add("gone"), 1800));
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
    pool,
    cards: [...interviews, ...FILES[lang]].map((card) => ({ badge: "", ...card })),
  });
  await page.waitForTimeout(400);
  const cards = page.locator(".hero-card");
  await record(page, id, async (rec) => {
    await rec.focus(union(await box(cards.first()), await box(cards.last())), 4, 20);
    await page.evaluate(() => (window as unknown as { heroPlay: () => void }).heroPlay());
    await rec.wait(1150);
    // Il processo intero, a tutto schermo, mentre si compone: nessuno zoom
    // sull'inizio (decisione del 14 ottobre, non si capiva).
    const poolNow = await box(page.locator(".process-bpmn-canvas [data-element-id^='DeliR_Pool']").first());
    await rec.focus(poolNow, 4, 8, { overview: true });
    await rec.wait(2900);
  });
}

// --- 2. Verifica il modello, insieme alle sue fonti.

async function momentEvidence(page: Page, lang: Lang, id: string): Promise<void> {
  await openCanvas(page, "Task_Verifica", 15);
  await page.getByRole("button", { name: UI[lang].evidence }).click();
  const panel = page.locator(".process-evidence-panel");
  await expect(panel).toBeVisible();
  await panel.locator("summary", { hasText: UI[lang].quoted }).click();
  const label = demoCase(lang).provenance.elements.find((item) => item.element_id === "Task_Verifica")!.label;
  const row = panel.locator("li").filter({ has: page.getByRole("button", { name: label, exact: true }) });
  const button = row.getByRole("button", { name: label, exact: true });
  await row.scrollIntoViewIfNeeded();
  // "Mostra nel disegno": l'attivita' si seleziona nel canvas. Poi la tela si
  // sposta perche' l'attivita' stia alla altezza della sua citazione, con lo
  // spazio per il collegamento.
  await button.click();
  await page.waitForTimeout(800);
  const task = node(page, "Task_Verifica");
  const area = await box(page.locator(".process-bpmn-canvas").first());
  const panelBox = await box(panel);
  const rowBox = await box(row);
  await page.mouse.move(area.x + area.width / 2, area.y + area.height / 2);
  // La rotella di bpmn-js non sposta di un pixel per pixel: si corregge a passi.
  for (let step = 0; step < 8; step++) {
    const now = await box(task);
    const dx = panelBox.x - 150 - (now.x + now.width);
    const dy = rowBox.y + rowBox.height / 2 - (now.y + now.height / 2);
    if (Math.abs(dx) < 12 && Math.abs(dy) < 12) break;
    await page.mouse.wheel(-dx, -dy);
    await page.waitForTimeout(200);
  }
  await page.waitForTimeout(500);
  await page.mouse.move(-10, -10);
  await calm(page);
  const quote = row.locator("blockquote").first();
  const taskBox = await box(task);
  const quoteBox = await box(quote);
  await row.evaluate((el) => el.setAttribute("data-hero-row", ""));
  // Il collegamento: la citazione si accende e una linea blu la porta
  // all'attivita' che regge, che si illumina.
  await page.evaluate(({ ease, from, to }) => {
    const style = document.createElement("style");
    style.textContent = `
      .hero-link { position: fixed; left: 0; top: 0; width: 100vw; height: 100vh; z-index: 70; pointer-events: none; overflow: visible; }
      .hero-link path { fill: none; stroke: #1d6fd8; stroke-width: 3; stroke-linecap: round; transition: stroke-dashoffset 700ms ${ease}; }
      .hero-link circle { fill: #1d6fd8; opacity: 0; transition: opacity 200ms ease-out; }
      .hero-link.on circle.from { opacity: 1; }
      .hero-link.done circle.to { opacity: 1; }
      .hero-quote { transition: background-color 300ms ease-out, box-shadow 300ms ease-out; border-radius: 8px; }
      .hero-quote.on { background-color: rgba(29, 111, 216, .1); box-shadow: inset 3px 0 0 #1d6fd8; }
      .hero-task > .djs-visual > rect { transition: stroke 300ms ease-out, fill 300ms ease-out, filter 300ms ease-out; }
      .hero-task.on > .djs-visual > rect { stroke: #1d6fd8 !important; stroke-width: 3px !important; fill: #eef5ff !important;
        filter: drop-shadow(0 0 8px rgba(29, 111, 216, .55)); }`;
    document.head.append(style);
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "hero-link");
    const a = { x: from.x - 6, y: from.y + Math.min(from.height / 2, 22) };
    const b = { x: to.x + to.width + 6, y: to.y + to.height / 2 };
    // Ad arco sopra il flusso: la linea non si confonde con il gateway accanto.
    const lift = Math.min(a.y, b.y) - 70;
    svg.innerHTML = `<path d="M ${a.x} ${a.y} C ${a.x - 60} ${lift}, ${b.x + 60} ${lift}, ${b.x} ${b.y}"/>`
      + `<circle class="from" cx="${a.x}" cy="${a.y}" r="5"/><circle class="to" cx="${b.x}" cy="${b.y}" r="5"/>`;
    document.body.append(svg);
    const path = svg.querySelector("path")!;
    const length = path.getTotalLength();
    path.style.strokeDasharray = `${length}`;
    path.style.strokeDashoffset = `${length}`;
    const quote = document.querySelector("[data-hero-row]");
    const taskEl = document.querySelector(".process-bpmn-canvas [data-element-id='Task_Verifica']");
    Object.assign(window, {
      heroLink: () => {
        quote?.classList.add("hero-quote", "on");
        svg.classList.add("on");
        setTimeout(() => { path.style.strokeDashoffset = "0"; }, 150);
        setTimeout(() => { svg.classList.add("done"); taskEl?.classList.add("hero-task", "on"); }, 800);
      },
    });
  }, { ease: EASE, from: quoteBox, to: taskBox });
  const scene = union(taskBox, await box(row), { x: taskBox.x, y: Math.min(taskBox.y, quoteBox.y) - 60, width: 1, height: 1 });
  await record(page, id, async (rec) => {
    // Una sola inquadratura: l'attivita' nel processo e la frase che la regge.
    await rec.focus(scene, 4, 2);
    await rec.wait(300);
    await moveTo(page, quote);
    await page.evaluate(() => (window as unknown as { heroLink: () => void }).heroLink());
    await rec.wait(1400);
    await moveTo(page, task);
    await rec.wait(1100);
  });
}

// --- 3. La simulazione As-Is: i casi scorrono, i KPI si muovono, poi la
// heatmap dell'intera esecuzione accende i colli di bottiglia in rosso.

/** Ctrl+rotella sulla tela della simulazione: lo zoom avviene nel prodotto. */
async function zoomSimulation(page: Page, target: Locator, steps: number): Promise<void> {
  const at = await box(target);
  await page.mouse.move(at.x + at.width / 2, at.y + at.height / 2);
  for (let step = 0; step < steps; step++) {
    await page.keyboard.down("Control");
    await page.mouse.wheel(0, -100);
    await page.keyboard.up("Control");
    await pauseFor(page, 120);
  }
}

const simNode = (page: Page, id: string) => page.locator(`.sim-analytical-canvas [data-element-id='${id}']`).first();

async function momentSimulation(page: Page, lang: Lang, id: string): Promise<void> {
  await page.goto(`${P}/simulation/replay/${IDS.asIsRun}`);
  const play = page.getByRole("button", { name: UI[lang].play, exact: true });
  await expect(play).toBeVisible();
  await page.getByRole("button", { name: UI[lang].showAll }).click().catch(() => undefined);
  // La seconda velocita' piu' rapida: in pochi secondi la coda si forma e i KPI si muovono.
  await page.getByRole("combobox", { name: UI[lang].speed }).click();
  const options = page.getByRole("option");
  await options.nth((await options.count()) - 2).click();
  await page.waitForTimeout(800);
  // Niente barra di zoom della tela sopra i KPI.
  await page.addStyleTag({ content: ".sim-scene-navigation { display: none !important; }" });
  await calm(page);
  // I quattro KPI (il tempo di attraversamento si disegna al primo caso chiuso).
  const charts = page.locator(".sim-widget");
  await expect(charts).toHaveCount(4);
  const process_ = await box(page.locator(".sim-analytical-canvas").first());
  const kpis = union(...(await Promise.all([0, 1, 2, 3].map((index) => box(charts.nth(index))))));
  const heatmap = page.getByRole("button", { name: UI[lang].heatmap }).first();
  const heatmapBox = await box(heatmap);
  await moveTo(page, { x: heatmapBox.x - 160, y: heatmapBox.y + 260 }, 10);
  const main = await box(page.locator("main").first());
  await record(page, id, async (rec) => {
    // Processo e KPI a tutta larghezza, mentre i casi scorrono.
    await rec.focus(union(process_, kpis), 4, 12, { overview: true });
    await play.click();
    await rec.wait(2000);
    // La heatmap dell'intera esecuzione: il collo di bottiglia diventa rosso,
    // poi la tela si ingrandisce su di lui.
    await rec.focus(main, 4, 0, { overview: true });
    await clickOn(page, heatmap, 500);
    const wholeRun = page.getByRole("button", { name: UI[lang].wholeRun });
    await rec.waitUntil(() => wholeRun.isVisible());
    await clickOn(page, wholeRun, 500);
    await rec.wait(300);
    await zoomSimulation(page, simNode(page, "Task_Valuta"), 3);
    await page.mouse.move(-10, -10);
    // La camera sul processo: il rosso si legge.
    await rec.focus(await box(page.locator(".sim-analytical-canvas").first()), 4, 8, { overview: true });
    await rec.wait(1500);
  });
}

// --- 4. Il To-Be: gli stessi colli di bottiglia diventano verdi, e di quanto
// migliora il processo.

async function momentToBe(page: Page, lang: Lang, id: string): Promise<void> {
  // A = As-Is, B = To-Be: la frase del confronto parla del miglioramento.
  await page.goto(`${P}/simulation/replay/${IDS.asIsRun}?a=${IDS.asIsRun}&b=${IDS.toBeRun}`);
  await expect(page.getByRole("button", { name: UI[lang].play, exact: true })).toBeVisible();
  await page.getByRole("button", { name: UI[lang].showAll }).click().catch(() => undefined);
  await page.addStyleTag({ content: ".sim-scene-navigation { display: none !important; }" });
  // Si riparte da dove finisce l'As-Is: heatmap rossa, tela ingrandita.
  await page.getByRole("button", { name: UI[lang].heatmap }).first().click();
  await page.getByRole("button", { name: UI[lang].wholeRun }).click();
  await page.waitForTimeout(600);
  await zoomSimulation(page, simNode(page, "Task_Valuta"), 3);
  await page.waitForTimeout(600);
  await calm(page);
  const compare = page.getByRole("button", { name: UI[lang].compare }).first();
  const compareBox = await box(compare);
  await moveTo(page, { x: compareBox.x - 140, y: compareBox.y + 260 }, 10);
  await record(page, id, async (rec) => {
    await rec.focus(await box(page.locator(".sim-analytical-canvas").first()), 4, 8, { overview: true });
    await rec.wait(300);
    await clickOn(page, compare, 600);
    const verdict = page.locator("p:has(> strong.font-semibold)").first();
    await rec.waitUntil(() => verdict.isVisible());
    await page.mouse.move(-10, -10);
    // Verde: quanto tempo si guadagna sulle stesse attivita'.
    await rec.wait(1500);
    // La frase: -87% di attraversamento, -43% di costo per caso.
    await rec.focus(await box(verdict), 4, 16);
    await rec.wait(2000);
  });
}

/**
 * Il link del cliente nasce dall'indirizzo della pagina: in ripresa sarebbe
 * quello di sviluppo. A schermo va il dominio vero, delir.it.
 */
async function showPublicLink(page: Page): Promise<void> {
  // Gia' quando il campo riceve il valore: nessun fotogramma con l'indirizzo locale.
  await page.evaluate((origin) => {
    const swap = (value: unknown) => (typeof value === "string" ? value.replace(origin, "https://delir.it") : value);
    const property = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!;
    Object.defineProperty(HTMLInputElement.prototype, "value", {
      ...property,
      set(this: HTMLInputElement, value: string) { property.set!.call(this, swap(value) as string); },
    });
    const setAttribute = Element.prototype.setAttribute;
    Element.prototype.setAttribute = function (name: string, value: string) {
      return setAttribute.call(this, name, name === "value" ? (swap(value) as string) : value);
    };
  }, new URL(page.url()).origin);
}

// --- 5. Il processo va al cliente: link privato, poi "in attesa della risposta".

async function momentSend(page: Page, lang: Lang, id: string): Promise<void> {
  await page.goto(`${P}/handover`);
  const send = page.getByRole("button", { name: UI[lang].send });
  await expect(send).toBeEnabled();
  await page.waitForTimeout(600);
  await calm(page);
  const banner = page.locator(".handover-status").first();
  const top = await box(banner);
  // Il cursore parte vicino al bottone: il primo gesto e' breve.
  const sendBox = await box(send);
  await moveTo(page, { x: sendBox.x - 120, y: sendBox.y + sendBox.height + 60 }, 10);
  await showPublicLink(page);
  await record(page, id, async (rec) => {
    // L'intestazione della consegna, con il bottone.
    await rec.focus(top, 4, 16, { overview: true });
    await clickOn(page, send, 700);
    const dialog = page.getByRole("dialog");
    const confirm = dialog.getByRole("button", { name: UI[lang].sent });
    await rec.waitUntil(() => confirm.isEnabled());
    await rec.focus(await box(dialog), 4, 16);
    await rec.wait(700);
    await clickOn(page, confirm, 800);
    await rec.waitUntil(async () => !(await dialog.isVisible()));
    // Inviato: lo stato della consegna passa a "con il cliente".
    await rec.focus(await box(banner), 4, 16, { overview: true });
    await rec.wait(1900);
  });
}

const MOMENTS = [
  ["1-fonti", momentSources],
  ["2-evidenze", momentEvidence],
  ["3-simulazione", momentSimulation],
  ["4-tobe", momentToBe],
  ["5-invio", momentSend],
] as const;

for (const lang of ["it", "en"] as const) {
  test.describe(`hero ${lang}`, () => {
    test.beforeEach(async ({ page }) => {
      page.setDefaultTimeout(20_000);
      // L'orologio della pagina: scorre normale, si ferma solo durante la ripresa.
      await page.clock.install();
      await installCaseApi(page, lang, { layout: "grid" });
      await installCursor(page);
    });
    for (const [name, moment] of MOMENTS) {
      const id = `hero-${lang}-${name}`;
      test(id, async ({ page }) => moment(page, lang, id));
    }
  });
}

// --- Le scritte del video, alla dimensione di ogni formato: la dicitura
// "caso dimostrativo" e le targhette blu che dicono cosa succede.

const TAGS = {
  it: ["Dalle fonti del cliente al processo", "Ogni attività con la sua fonte", "Simula l'As-Is: ecco il collo di bottiglia", "Il To-Be: da rosso a verde, −87% di tempo", "Invia il processo al cliente"],
  en: ["From client sources to the process", "Every activity backed by its source", "Simulate the As-Is: here is the bottleneck", "The To-Be: from red to green, −87% time", "Send the process to the client"],
} as const;

test("hero-overlays", async ({ page }) => {
  mkdirSync(OVERLAYS, { recursive: true });
  for (const lang of ["it", "en"] as const) {
    for (const [format, size, font, tag] of [["16x9", [1920, 1080], 28, 36]] as const) {
      await page.setViewportSize({ width: size[0], height: size[1] });
      await page.setContent(`<!doctype html><html><body style="margin:0;background:transparent">
        <div style="position:fixed;right:${font}px;bottom:${font}px;padding:${font * 0.35}px ${font * 0.7}px;border-radius:999px;
          background:rgba(255,255,255,.92);border:1px solid #e2e8f0;color:#334155;font:500 ${font}px/1.2 system-ui,sans-serif">${UI[lang].demo}</div>
        </body></html>`);
      await page.screenshot({ path: resolve(OVERLAYS, `dimostrativo-${lang}-${format}.png`), omitBackground: true });
      for (const [index, text] of TAGS[lang].entries()) {
        // In alto a sinistra, nel blu del marchio: il numero del passo e la frase.
        await page.setContent(`<!doctype html><html><body style="margin:0;background:transparent">
          <div style="position:fixed;left:${tag}px;top:${tag}px;max-width:${size[0] - 2 * tag}px;display:flex;align-items:center;gap:${tag * 0.4}px;
            padding:${tag * 0.38}px ${tag * 0.75}px ${tag * 0.38}px ${tag * 0.38}px;border-radius:999px;background:#004580;color:#fff;
            box-shadow:0 ${tag * 0.3}px ${tag}px -${tag * 0.4}px rgba(0,30,70,.55);font:600 ${tag}px/1.2 system-ui,sans-serif">
            <span style="display:grid;place-items:center;width:${tag * 1.35}px;height:${tag * 1.35}px;border-radius:999px;background:#fff;color:#004580;font-weight:700">${index + 1}</span>
            <span>${text}</span></div>
          </body></html>`);
        await page.screenshot({ path: resolve(OVERLAYS, `tag-${lang}-${index + 1}-${format}.png`), omitBackground: true });
      }
    }
  }
});
