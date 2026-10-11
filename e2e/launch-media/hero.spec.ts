/**
 * Il video hero della landing: cinque inquadrature reali del prodotto, in
 * inglese, montate in un loop di 10 s (docs/launch/hero-video.md).
 *
 *   npm run media:hero
 *
 * Niente cursore e niente testo nel browser: le didascalie le mette il
 * montaggio. Ogni ripresa prepara lo stato finale, lo nasconde, poi lo fa
 * comparire con transizioni CSS sopra l'interfaccia vera: il movimento e' una
 * funzione del tempo, quindi ogni registrazione e' uguale alla precedente.
 */
import { expect, test, type Page } from "@playwright/test";
import { resolve } from "node:path";

import { IDS } from "./demo";
import { HERO_SOURCES } from "./heroLocale";
import { installDemoApi, unhandled } from "./mockApi";
import { Recorder } from "./recorder";
import storyboard from "./storyboard.json";

const RAW = resolve(process.cwd(), "artifacts", "launch-media", "raw");
const P = `/projects/${IDS.project}/processes/${IDS.process}`;
const EASE = "cubic-bezier(.22,1,.36,1)";

test.skip(Boolean(process.env.CI) && process.env.DELIR_LAUNCH_MEDIA !== "1", "Generatore di media: in CI con DELIR_LAUNCH_MEDIA=1");
// 1440x810 a densita' 4/3: fotogrammi 1920x1080 con l'interfaccia un terzo piu' grande.
test.use({ viewport: { width: 1440, height: 810 }, deviceScaleFactor: 4 / 3 });

test.beforeEach(async ({ page }) => {
  page.setDefaultTimeout(15_000);
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

/** Toglie i caret, gli outline di focus e le animazioni di caricamento rimaste. */
async function calm(page: Page): Promise<void> {
  await page.addStyleTag({ content: "*:focus, *:focus-visible { outline: none !important; box-shadow: none !important; } * { caret-color: transparent !important; }" });
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
}

// --- 1. Conoscenza sparsa: quattro file entrano nelle righe della scheda Sources.

test("hero-sources", async ({ page }) => {
  await page.goto(`/projects/${IDS.project}`);
  await page.getByRole("tab", { name: /Sources/ }).click();
  await expect(page.getByText(HERO_SOURCES[3].title)).toBeVisible();
  await calm(page);
  await page.waitForTimeout(500);
  await page.evaluate(({ sources, ease }) => {
    const rows = sources.map((source) => {
      const title = [...document.querySelectorAll("main *")].find((el) => el.children.length === 0 && el.textContent === source.title) as HTMLElement;
      // La riga intera: il primo antenato i cui fratelli sono le altre righe.
      let row: HTMLElement = title;
      while (row.parentElement && row.parentElement.children.length < sources.length) row = row.parentElement;
      return row;
    });
    const count = [...document.querySelectorAll("main *")].find((el) => el.children.length === 0 && /\d of \d sources/.test(el.textContent ?? "")) as HTMLElement | undefined;
    const style = document.createElement("style");
    style.textContent = `
      .hero-row { opacity: 0; transform: translateY(6px); transition: opacity 360ms ${ease}, transform 360ms ${ease}; }
      .hero-row.in { opacity: 1; transform: none; }
      .hero-file { position: fixed; z-index: 50; display: flex; align-items: center; gap: 12px; padding: 12px 16px; width: 290px;
        background: #fff; border: 1px solid #dfe1e5; border-radius: 14px; box-shadow: 0 18px 40px -18px rgba(15,23,42,.35), 0 2px 6px rgba(15,23,42,.06);
        font: 500 15px/1.25 "Geist Variable", Geist, system-ui, sans-serif; color: #0f172a;
        transition: transform 900ms ${ease}, opacity 260ms ease-out; }
      .hero-file small { display: block; margin-top: 2px; font-size: 12px; font-weight: 450; color: #64748b; }
      .hero-file b { flex: none; display: grid; place-items: center; width: 38px; height: 44px; border-radius: 7px; font-size: 10px; font-weight: 700; letter-spacing: .04em; color: #fff; }
      .hero-file.gone { opacity: 0; }`;
    document.head.append(style);
    rows.forEach((row) => row.classList.add("hero-row"));
    count?.classList.add("hero-row");
    const look = [
      { tag: "PDF", color: "#dc2626", note: "Procedure · 12 pages", dx: -330, dy: -150, rot: -7 },
      { tag: "TXT", color: "#7c3aed", note: "Interview transcript · 48 min", dx: 360, dy: -120, rot: 6 },
      { tag: "XLS", color: "#15803d", note: "Spreadsheet · 412 rows", dx: -300, dy: 190, rot: 5 },
      { tag: "DOC", color: "#d97706", note: "Meeting notes", dx: 340, dy: 170, rot: -5 },
    ];
    const list = rows[0].parentElement!.getBoundingClientRect();
    const cx = list.left + list.width / 2;
    const cy = list.top + list.height / 2 + 40;
    const cards = sources.map((source, index) => {
      const target = rows[index].getBoundingClientRect();
      const card = document.createElement("div");
      card.className = "hero-file";
      card.innerHTML = `<b style="background:${look[index].color}">${look[index].tag}</b><span>${source.title}<small>${look[index].note}</small></span>`;
      document.body.append(card);
      // Parte sparsa intorno alla lista, arriva sopra la sua riga.
      const sx = cx + look[index].dx - 145;
      const sy = cy + look[index].dy - 34;
      card.style.left = `${sx}px`;
      card.style.top = `${sy}px`;
      card.style.transform = `rotate(${look[index].rot}deg)`;
      card.dataset.to = `translate(${target.left + 52 - sx}px, ${target.top + target.height / 2 - 34 - sy}px) rotate(0deg) scale(.92)`;
      return card;
    });
    Object.assign(window, {
      heroPlay: () => {
        cards.forEach((card, index) => setTimeout(() => { card.style.transform = card.dataset.to!; }, 150 + index * 110));
        cards.forEach((card, index) => setTimeout(() => { card.classList.add("gone"); rows[index].classList.add("in"); }, 1150 + index * 110));
        setTimeout(() => count?.classList.add("in"), 1600);
      },
    });
  }, { sources: HERO_SOURCES, ease: EASE });
  await record(page, "hero-sources", async () => {
    await page.waitForTimeout(300);
    await page.evaluate(() => (window as unknown as { heroPlay: () => void }).heroPlay());
    await page.waitForTimeout(2300);
  });
});

// --- 2. As-Is verificato: il processo si compone, poi le evidenze.

test("hero-asis", async ({ page }) => {
  await page.goto(`${P}?view=canvas`);
  await expect(page.locator("[data-element-id='percorso_autorizzazione_autorizza_spesa']").first()).toBeVisible();
  // Il pannello si apre prima di registrare: la tela non si ridimensiona in scena.
  await page.getByRole("button", { name: /Review the drawing against the evidence/ }).first().click();
  const panel = page.getByRole("complementary", { name: "Drawing evidence" });
  await expect(panel).toContainText("100%");
  await calm(page);
  await page.waitForTimeout(600);
  await page.evaluate((ease) => {
    const style = document.createElement("style");
    style.textContent = `
      .hero-el > .djs-visual { opacity: 0; transform: translateX(-8px); transition: opacity 420ms ${ease}, transform 420ms ${ease}; }
      .hero-el.in > .djs-visual { opacity: 1; transform: none; }
      .hero-panel { opacity: 0; transform: translateX(28px); transition: opacity 520ms ${ease}, transform 520ms ${ease}; }
      .hero-panel.in { opacity: 1; transform: none; }`;
    document.head.append(style);
    const elements = [...document.querySelectorAll<SVGGElement>(".djs-container .djs-element")]
      .filter((el) => !el.closest(".djs-drag-group"))
      .map((el) => ({ el, box: el.getBoundingClientRect() }))
      .filter(({ box }) => box.width > 0);
    // Prima pool e corsie, poi gli elementi da sinistra a destra.
    const frame = elements.filter(({ box }) => box.width > 600);
    const flow = elements.filter(({ box }) => box.width <= 600).sort((a, b) => a.box.left - b.box.left);
    const left = Math.min(...flow.map(({ box }) => box.left));
    const right = Math.max(...flow.map(({ box }) => box.left));
    [...frame, ...flow].forEach(({ el }) => el.classList.add("hero-el"));
    const aside = document.querySelector("[aria-label='Drawing evidence']") as HTMLElement;
    aside?.classList.add("hero-panel");
    Object.assign(window, {
      heroPlay: () => {
        frame.forEach(({ el }) => el.classList.add("in"));
        flow.forEach(({ el, box }) => setTimeout(() => el.classList.add("in"), 200 + ((box.left - left) / Math.max(1, right - left)) * 1000));
        setTimeout(() => aside?.classList.add("in"), 1350);
      },
    });
  }, EASE);
  await record(page, "hero-asis", async () => {
    await page.waitForTimeout(200);
    await page.evaluate(() => (window as unknown as { heroPlay: () => void }).heroPlay());
    await page.waitForTimeout(2600);
  });
});

// --- 3. Cosa cambiare: la heatmap sullo stesso processo, il collo di bottiglia.

test("hero-heatmap", async ({ page }) => {
  await page.goto(`${P}/simulation/heatmap/${IDS.asIsRun}`);
  await expect(page.getByText("Bottleneck").first()).toBeVisible({ timeout: 30_000 });
  await calm(page);
  await page.waitForTimeout(1200);
  const node = page.locator("[data-element-id='percorso_autorizzazione_autorizza_spesa']").first();
  const card = page.getByText("Approve spend", { exact: true }).last();
  const a = (await node.boundingBox())!;
  const b = (await card.locator("xpath=ancestor::*[contains(@class,'rounded') or self::section][1]").boundingBox()) ?? (await card.boundingBox())!;
  const rect = { x: Math.min(a.x, b.x), y: Math.min(a.y, b.y) - 20, width: Math.max(a.x + a.width, b.x + b.width) - Math.min(a.x, b.x), height: 0 };
  // Il nodo e la testata della scheda (nome, "Bottleneck", attesa media): non tutta la scheda.
  rect.height = Math.max(a.y + a.height, b.y + 120) - rect.y;
  await record(page, "hero-heatmap", async (rec) => {
    await page.waitForTimeout(150);
    await rec.focus(rect, 1.7, 16);
    await page.waitForTimeout(1900);
  });
});

// --- 4. Testa prima di raccomandare: il workspace AS-IS | A | B.

test("hero-scenarios", async ({ page }) => {
  await page.goto(`${P}/simulation/workspace/${IDS.asIsRun}?panel=scenarios`);
  const workspace = page.locator("[data-sim-scenario-workspace]");
  await expect(workspace.locator('[data-sim-workspace-row="B"]')).toContainText("Better");
  // Il pannello piu' largo: tre scenari e i loro KPI senza andare a capo.
  const splitter = page.getByRole("separator", { name: "Resize details panel" });
  await splitter.focus();
  for (let step = 0; step < 22; step += 1) await page.keyboard.press("ArrowLeft");
  await calm(page);
  await page.waitForTimeout(800);
  await workspace.locator(".sim-workspace-table").scrollIntoViewIfNeeded();
  await page.waitForTimeout(300);
  await page.evaluate((ease) => {
    const style = document.createElement("style");
    style.textContent = `
      [data-sim-workspace-row] { opacity: 0; transform: translateY(8px); transition: opacity 380ms ${ease}, transform 380ms ${ease}, background-color 500ms ease; }
      [data-sim-workspace-row].in { opacity: 1; transform: none; }
      [data-sim-workspace-row="B"].win { background-color: color-mix(in srgb, var(--state-success-text, #15803d) 9%, transparent); }`;
    document.head.append(style);
    const rows = [...document.querySelectorAll<HTMLElement>("[data-sim-workspace-row]")];
    Object.assign(window, {
      heroPlay: () => {
        rows.forEach((row, index) => setTimeout(() => row.classList.add("in"), 150 + index * 330));
        setTimeout(() => rows.find((row) => row.dataset.simWorkspaceRow === "B")?.classList.add("win"), 1000);
      },
    });
  }, EASE);
  const table = (await workspace.locator(".sim-workspace-table").boundingBox())!;
  await record(page, "hero-scenarios", async (rec) => {
    await rec.focus({ x: table.x - 12, y: table.y - 12, width: table.width + 24, height: Math.min(table.height + 24, 520) }, 1.35, 0);
    await page.waitForTimeout(150);
    await page.evaluate(() => (window as unknown as { heroPlay: () => void }).heroPlay());
    await page.waitForTimeout(2700);
  });
});

// --- 5. Continua a migliorare: lo scenario B sul processo, che intanto gira.

test("hero-improve", async ({ page }) => {
  await page.goto(`${P}/simulation/workspace/${IDS.asIsRun}?panel=scenario&scenario=3`);
  await expect(page.locator(".sim-process-legend")).toContainText("scenario B");
  const tabs = page.locator("[data-sim-scenario-tabs]");
  await expect(tabs).toContainText("changes from the AS-IS");
  const splitter = page.getByRole("separator", { name: "Resize details panel" });
  await splitter.focus();
  for (let step = 0; step < 14; step += 1) await page.keyboard.press("ArrowLeft");
  await calm(page);
  await page.waitForTimeout(1000);
  const changed = (await page.locator('.djs-element[data-element-id="ricostruisci_richiesta"]').first().boundingBox())!;
  const panel = (await tabs.boundingBox())!;
  await page.evaluate((ease) => {
    const style = document.createElement("style");
    style.textContent = `.sim-scenario-changed .djs-visual > :first-child { transition: stroke-width 400ms ${ease}; }`;
    document.head.append(style);
  }, EASE);
  await record(page, "hero-improve", async (rec) => {
    // Il processo gira con lo scenario B: il miglioramento continua.
    await page.getByRole("button", { name: "Play", exact: true }).click().catch(() => undefined);
    await calm(page);
    await rec.focus({ x: changed.x - 110, y: changed.y - 90, width: panel.x + panel.width - changed.x + 120, height: panel.y + 330 - changed.y + 90 }, 1.4, 0);
    await page.waitForTimeout(2600);
  });
});

// --- Didascalie: chip piccole in alto a sinistra, sopra l'interfaccia (PNG trasparenti).

test("hero-overlays", async ({ page }) => {
  const dir = resolve(process.cwd(), "artifacts", "launch-media", "overlays");
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/home");
  const font = (await page.evaluate(() => getComputedStyle(document.body).fontFamily)).replace(/"/g, "'");
  const esc = (text: string) => text.replace(/&/g, "&amp;").replace(/</g, "&lt;");
  const render = async (name: string, body: string) => {
    await page.setContent(`<!doctype html><html><body style="margin:0;background:transparent;font-family:${font}">${body}</body></html>`);
    await page.screenshot({ path: resolve(dir, `${name}.png`), omitBackground: true });
  };
  for (const scene of storyboard.scenes.filter((item) => "chip" in item)) {
    await render(`chip-${scene.id}`, `<div style="position:fixed;left:116px;top:16px;display:inline-flex;align-items:center;gap:12px;padding:12px 22px 12px 16px;border-radius:999px;background:rgba(15,23,42,.92);box-shadow:0 10px 30px -10px rgba(15,23,42,.45);color:#fff;font-size:30px;font-weight:600;letter-spacing:-0.01em">
      <span style="width:12px;height:12px;border-radius:50%;background:#60a5fa"></span>${esc((scene as { chip: string }).chip)}</div>`);
  }
  await render("disclaimer-hero", `<div style="position:fixed;right:18px;bottom:14px;font-size:17px;color:#475569;background:rgba(255,255,255,.92);border:1px solid #e2e8f0;border-radius:999px;padding:6px 14px">Demo data · simulated example</div>`);
});
