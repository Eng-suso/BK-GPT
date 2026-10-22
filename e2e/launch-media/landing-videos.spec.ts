/**
 * I video della landing (docs/launch/landing-videos.md): Problem, Agitate, le
 * quattro scene Solve e il percorso completo, dalle stesse registrazioni.
 *
 *   npm run media:landing            # cattura + montaggio
 *
 * Regole di regia: il prodotto si vede sempre per intero, ritmo lento, camera
 * ferma (uno zoom leggero solo mentre si scrive), targhette IT/EN su cio' che
 * accade. Ogni `tag(rec, ...)` segna l'istante in cui cambia la targhetta; i
 * testi stanno in landing-videos.json, il montaggio in
 * scripts/landing_videos_edit.py. Processo: il caso semplice (simpleData.ts).
 */
import { expect, test, type Locator, type Page } from "@playwright/test";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

import { IDS } from "./demo";
import { installDemoApi, unhandled } from "./mockApi";
import { Recorder, clickOn, cue, installCursor, moveTo, slowScroll } from "./recorder";
import { simpleDiscoveryQuestion } from "./simpleData";
import script from "./landing-videos.json";

const OUT = resolve(process.cwd(), "artifacts", "landing-videos");
const RAW = resolve(OUT, "raw");
const P = `/projects/${IDS.project}/processes/${IDS.process}`;
// Il ritmo: movimenti lenti del cursore e pause per leggere.
const MOVE = 1300;
const READ = 2600;

test.skip(Boolean(process.env.CI) && process.env.DELIR_LAUNCH_MEDIA !== "1", "Generatore di media: in CI con DELIR_LAUNCH_MEDIA=1");
// 1440x810 a densita' 4/3: fotogrammi 1920x1080, interfaccia un terzo piu' grande.
test.use({ viewport: { width: 1440, height: 810 }, deviceScaleFactor: 4 / 3 });

test.beforeEach(async ({ page }, info) => {
  page.setDefaultTimeout(15_000);
  await installDemoApi(page, "it", { simple: true, live: info.title === "lv-chat" });
  await installCursor(page);
  // Il watermark del disegno, i controlli flottanti della tela (coprirebbero i
  // KPI), i contorni di focus e il caret non entrano nei video.
  await page.addInitScript(() => {
    const style = document.createElement("style");
    style.textContent = ".bjs-powered-by { display: none !important; } .sim-scene-controls { opacity: 0 !important; } *:focus-visible { outline: none !important; } input, textarea { caret-color: transparent; }";
    document.addEventListener("DOMContentLoaded", () => document.head.append(style));
  });
});

test.afterAll(() => {
  if (unhandled.size) console.warn("Richieste non coperte dal caso demo:", [...unhandled].join(", "));
});

function tag(rec: Recorder, key: string): void {
  rec.mark(`tag:${key}`);
}

async function scene(page: Page, id: string, setup: () => Promise<void>, act: (rec: Recorder) => Promise<void>): Promise<void> {
  await setup();
  await page.waitForTimeout(800);
  const rec = new Recorder(page, resolve(RAW, id));
  await rec.start();
  await act(rec);
  await page.waitForTimeout(1200);
  rec.mark("end");
  await rec.stop();
}

async function read(page: Page, ms = READ): Promise<void> {
  await page.waitForTimeout(ms);
}

async function scrollable(container: Locator): Promise<Locator> {
  const index = await container.evaluate((root) => {
    const all = [root, ...Array.from(root.querySelectorAll("*"))] as HTMLElement[];
    return all.findIndex((el) => el.scrollHeight > el.clientHeight + 40 && /(auto|scroll)/.test(getComputedStyle(el).overflowY));
  });
  return index <= 0 ? container : container.locator("*").nth(index - 1);
}

// --- Problem, Agitate: il punto di partenza, dentro DeliR ---------------------
// Solo schermate del prodotto: le interviste grezze, poi cio' che il processo
// di oggi lascia aperto (la soglia che nessuno dice, chi fa cosa, l'attesa).

/** Il contenitore che scorre attorno a un elemento (l'elemento stesso o un antenato). */
async function scrollerOf(target: Locator): Promise<Locator> {
  await target.evaluate((el) => {
    let node: HTMLElement | null = el as HTMLElement;
    while (node && !(node.scrollHeight > node.clientHeight + 20 && /(auto|scroll)/.test(getComputedStyle(node).overflowY))) node = node.parentElement;
    document.querySelectorAll("[data-lv-scroller]").forEach((item) => item.removeAttribute("data-lv-scroller"));
    node?.setAttribute("data-lv-scroller", "");
  });
  return target.page().locator("[data-lv-scroller]");
}

/** Porta in vista una sezione del dialogo della fonte, scorrendo piano. */
async function scrollToText(page: Page, dialog: Locator, text: RegExp, ms: number): Promise<void> {
  const box = await scrollable(dialog);
  const offset = await dialog.getByText(text).first().evaluate((el) => {
    let node: HTMLElement | null = el as HTMLElement;
    let top = 0;
    while (node && !(node.scrollHeight > node.clientHeight + 40 && /(auto|scroll)/.test(getComputedStyle(node).overflowY))) {
      top += node.offsetTop;
      node = node.offsetParent as HTMLElement | null;
    }
    return top;
  });
  const now = await box.evaluate((el) => el.scrollTop);
  await slowScroll(page, box, Math.max(0, offset - 40) - now, ms);
}

test("lv-problem", async ({ page }) => {
  await scene(page, "lv-problem", async () => {
    await page.goto(`/projects/${IDS.project}`);
    await page.getByRole("tab", { name: /Fonti/ }).click();
    await expect(page.getByText("Intervista Paolo Marchetti").first()).toBeVisible();
  }, async (rec) => {
    tag(rec, "interviews");
    await read(page, 1400);
    for (const name of ["Laura Conti", "Paolo Marchetti", "Francesca Neri"]) {
      await moveTo(page, page.getByText(`Intervista ${name}`).first(), 1000);
      await read(page, 700);
    }
    await clickOn(page, page.getByText("Intervista Paolo Marchetti").first(), MOVE);
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByText(/TESTO DELLA FONTE/i).first()).toBeAttached();
    await read(page, 900);
    tag(rec, "text");
    await scrollToText(page, dialog, /TESTO DELLA FONTE/i, 3600);
    await read(page, 1600);
    await read(page, 1200);
    tag(rec, "scattered");
    // Il testo della fonte ha il suo riquadro: lo si legge scorrendo piano.
    await slowScroll(page, await scrollerOf(dialog.getByText(/Intervista 2 — Paolo Marchetti/).first()), 760, 8200);
    await read(page, 2000);
    tag(rec, "manual");
    await page.keyboard.press("Escape");
    await read(page, 800);
    await clickOn(page, page.getByText("Intervista Laura Conti").first(), MOVE);
    const laura = page.getByRole("dialog");
    await expect(laura.getByText(/TESTO DELLA FONTE/i).first()).toBeAttached();
    await read(page, 900);
    await scrollToText(page, laura, /TESTO DELLA FONTE/i, 3600);
    await read(page, 1000);
    await slowScroll(page, await scrollerOf(laura.getByText(/Intervista 1 — Laura Conti/).first()), 900, 6000);
    await read(page, 2400);
  });
});

test("lv-agitate", async ({ page }) => {
  await scene(page, "lv-agitate", async () => {
    await page.goto(P);
    await expect(page.getByRole("button", { name: /^Decidi$/ })).toBeVisible();
  }, async (rec) => {
    tag(rec, "assumption");
    await read(page, 1000);
    await clickOn(page, page.getByRole("button", { name: /^Decidi$/ }), MOVE);
    await read(page, 1000);
    await clickOn(page, page.getByRole("button", { name: /Da decidere/ }), MOVE);
    await read(page, 1200);
    await moveTo(page, page.getByText(/Qual e' la soglia di importo/).first(), MOVE);
    await read(page, 3600);
    tag(rec, "who");
    await page.goto(`/projects/${IDS.project}`);
    await page.getByRole("tab", { name: /Fonti/ }).click();
    await read(page, 900);
    await clickOn(page, page.getByText("Intervista Paolo Marchetti").first(), MOVE);
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByText(/CONFRONTO CON GLI ALTRI FILE/i).first()).toBeAttached();
    await read(page, 600);
    await scrollToText(page, dialog, /CONFRONTO CON GLI ALTRI FILE/i, 3000);
    await moveTo(page, dialog.getByText(/non voglio dirti un nome a caso/).last(), MOVE);
    await read(page, 2000);
    await moveTo(page, dialog.getByText(/onestamente non e' mai stato detto/).first(), MOVE);
    await read(page, 2600);
    tag(rec, "wait");
    await page.goto(`${P}/simulation/heatmap/${IDS.asIsRun}`);
    await expect(page.getByText("Collo di bottiglia").first()).toBeVisible();
    await page.getByRole("button", { name: "Mostra tutta la tela" }).click();
    await read(page, 1400);
    await moveTo(page, page.locator("[data-element-id='approve_spend']").first(), MOVE);
    await read(page, 2000);
    await moveTo(page, page.getByText(/ATTESA MEDIA/i).first(), MOVE);
    await read(page, 3600);
  });
});

// --- Solve: Process Discovery ------------------------------------------------

test("lv-sources", async ({ page }) => {
  await scene(page, "lv-sources", async () => {
    await page.goto(`/projects/${IDS.project}`);
    await expect(page.getByRole("tab", { name: /Fonti/ })).toBeVisible();
  }, async (rec) => {
    tag(rec, "open");
    await read(page, 1200);
    await clickOn(page, page.getByRole("tab", { name: /Fonti/ }), MOVE);
    await read(page, 1800);
    for (const name of ["Laura Conti", "Paolo Marchetti", "Francesca Neri"]) {
      await moveTo(page, page.getByText(`Intervista ${name}`).first(), 900);
      await read(page, 500);
    }
    tag(rec, "laura");
    await clickOn(page, page.getByText("Intervista Laura Conti").first(), MOVE);
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByText("citazione verificata").first()).toBeVisible();
    await read(page, 1800);
    tag(rec, "verified");
    await moveTo(page, dialog.getByText("citazione verificata").first(), MOVE);
    await read(page, 1400);
    await slowScroll(page, await scrollable(dialog), 420, 5200);
    await read(page, 1600);
    tag(rec, "francesca");
    await page.keyboard.press("Escape");
    await read(page, 900);
    await clickOn(page, page.getByText("Intervista Francesca Neri").first(), MOVE);
    const other = page.getByRole("dialog");
    await expect(other.getByText(/CONFRONTO CON GLI ALTRI FILE/i).first()).toBeAttached();
    await read(page, 1600);
    const box = await scrollable(other);
    const offset = await other.getByText(/CONFRONTO CON GLI ALTRI FILE/i).first().evaluate((el) => {
      let node: HTMLElement | null = el as HTMLElement;
      let top = 0;
      while (node && !(node.scrollHeight > node.clientHeight + 40 && /(auto|scroll)/.test(getComputedStyle(node).overflowY))) {
        top += node.offsetTop;
        node = node.offsetParent as HTMLElement | null;
      }
      return top;
    });
    await slowScroll(page, box, Math.max(0, offset - 40), 4200);
    tag(rec, "divergence");
    await read(page, 900);
    await moveTo(page, other.getByText(/Divergenze/).first(), MOVE);
    await read(page, 1600);
    await moveTo(page, other.getByText(/la faccio io/).first(), MOVE);
    await read(page, 3200);
  });
});

test("lv-chat", async ({ page }) => {
  await scene(page, "lv-chat", async () => {
    await page.goto(P);
    await expect(page.getByPlaceholder(/Scrivi un messaggio/)).toBeVisible();
  }, async (rec) => {
    tag(rec, "ask");
    const box = page.getByPlaceholder(/Scrivi un messaggio/);
    await read(page, 1000);
    // L'unico zoom: mentre si scrive, sul campo del messaggio.
    await rec.focus(page.locator("form").filter({ has: box }).first(), 1.3, 40);
    await clickOn(page, box, MOVE);
    const started = Date.now();
    await box.pressSequentially(simpleDiscoveryQuestion, { delay: 45 });
    cue("type", { count: simpleDiscoveryQuestion.length, length: (Date.now() - started) / 1000 }, (started - Date.now()) / 1000);
    await read(page, 900);
    rec.wide();
    await read(page, 600);
    await page.keyboard.press("Enter");
    tag(rec, "working");
    await moveTo(page, { x: 1300, y: 760 }, MOVE);
    await expect(page.getByText(/Leggo le fonti raccolte/).first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(/due ruoli/).first()).toBeVisible({ timeout: 40_000 });
    tag(rec, "answer");
    await expect(page.getByRole("button", { name: /Ferma/ })).toBeHidden({ timeout: 40_000 });
    await read(page, 4200);
    tag(rec, "gap");
    const decide = page.getByRole("button", { name: /^Decidi$/ });
    if (await decide.isVisible().catch(() => false)) {
      await clickOn(page, decide, MOVE);
      await read(page, 1200);
      const pending = page.getByRole("button", { name: /Da decidere/ });
      if (await pending.isVisible().catch(() => false)) await clickOn(page, pending, MOVE);
      await read(page, 1200);
      await moveTo(page, page.getByText(/soglia/).first(), MOVE);
    }
    await read(page, 3400);
  });
});

// --- Solve: Evidence & BPMN ---------------------------------------------------

test("lv-evidence", async ({ page }) => {
  await scene(page, "lv-evidence", async () => {
    await page.goto(`${P}?view=canvas`);
    await expect(page.locator("[data-element-id='approve_spend']").first()).toBeVisible();
    await page.getByRole("button", { name: "Centra" }).click().catch(() => undefined);
  }, async (rec) => {
    tag(rec, "canvas");
    await read(page, 1400);
    for (const id of ["start", "send_request", "check_request", "gw_complete", "approve_spend", "issue_po", "end"]) {
      await moveTo(page, page.locator(`[data-element-id='${id}']`).first(), 800);
      await read(page, 350);
    }
    tag(rec, "evidence");
    await clickOn(page, page.getByRole("button", { name: "Evidenze" }), MOVE);
    const panel = page.getByRole("complementary", { name: "Evidenze del disegno" });
    await expect(panel).toContainText("100%");
    await page.getByRole("button", { name: "Centra" }).click().catch(() => undefined);
    await read(page, 1200);
    await moveTo(page, panel.getByText("Il disegno coincide con le fonti"), MOVE);
    await read(page, 1800);
    await moveTo(page, panel.getByText("100%").first(), 900);
    await read(page, 1600);
    tag(rec, "quotes");
    await clickOn(page, panel.locator("summary", { hasText: "Citati dalle fonti" }), MOVE);
    await read(page, 1400);
    for (const label of ["Invia richiesta di acquisto", "Verifica richiesta", "Autorizza spesa"]) {
      const item = panel.getByText(label, { exact: true }).first();
      await item.evaluate((el) => el.scrollIntoView({ behavior: "smooth", block: "center" })).catch(() => undefined);
      await read(page, 900);
      await moveTo(page, item, MOVE);
      await read(page, 2000);
    }
    tag(rec, "versions");
    await clickOn(page, page.getByRole("button", { name: "Importa, esporta, cronologia" }), MOVE);
    await read(page, 600);
    await clickOn(page, page.getByRole("menuitem", { name: /Cronologia versioni/ }), MOVE);
    await read(page, 1200);
    for (const text of ["Prima bozza dalle tre interviste", "As-Is v3 · validato con Laura Conti"]) {
      await moveTo(page, page.getByText(text).first(), MOVE);
      await read(page, 1800);
    }
    await read(page, 1400);
  });
});

test("lv-hypotheses", async ({ page }) => {
  await scene(page, "lv-hypotheses", async () => {
    await page.goto(P);
    await expect(page.getByRole("tab", { name: "Ipotesi To-Be" })).toBeVisible();
  }, async (rec) => {
    tag(rec, "list");
    await read(page, 1000);
    await clickOn(page, page.getByRole("tab", { name: "Ipotesi To-Be" }), MOVE);
    await expect(page.getByText("La richiesta nasce completa, con i campi obbligatori")).toBeVisible();
    await read(page, 1400);
    await moveTo(page, page.getByText("La richiesta nasce completa, con i campi obbligatori"), MOVE);
    await read(page, 1400);
    await moveTo(page, page.getByText(/Un posto unico dove la richiesta/).first(), MOVE);
    await read(page, 3000);
    tag(rec, "second");
    await moveTo(page, page.getByText(/Autorizzazione visibile/).first(), MOVE);
    await read(page, 1400);
    await moveTo(page, page.getByText(/vorrei che l'autorizzazione/).first(), MOVE);
    await read(page, 3200);
  });
});

// --- Solve: Analysis & Simulation -------------------------------------------

async function replay(page: Page, id: string, run: number, beats: [number, string][], cut: number, total: number): Promise<void> {
  await scene(page, id, async () => {
    await page.goto(`${P}/simulation/replay/${run}`);
    await expect(page.getByRole("button", { name: "Riproduci", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Mostra tutta la tela" }).click();
    await page.getByRole("combobox", { name: "Velocità" }).click();
    await page.getByRole("option", { name: "≈ 40 s" }).click();
    await page.waitForTimeout(900);
  }, async (rec) => {
    tag(rec, beats[0][1]);
    await read(page, 1600);
    await clickOn(page, page.getByRole("button", { name: "Riproduci", exact: true }), MOVE);
    const started = Date.now();
    await moveTo(page, { x: 1400, y: 790 }, MOVE);
    for (const [at, key] of beats.slice(1)) {
      await page.waitForTimeout(Math.max(0, at * 1000 - (Date.now() - started)));
      tag(rec, key);
    }
    await page.waitForTimeout(Math.max(0, cut * 1000 - (Date.now() - started)));
    rec.mark("cut");
    await page.waitForTimeout(Math.max(0, total * 1000 - (Date.now() - started)));
  });
}

test("lv-sim-asis", ({ page }) => replay(page, "lv-sim-asis", IDS.asIsRun, [[0, "start"], [2.5, "flow"], [8, "queue"], [15, "kpi"]], 22, 40));
test("lv-sim-tobe", ({ page }) => replay(page, "lv-sim-tobe", IDS.toBeRun, [[0, "start"], [4, "flow"], [10, "kpi"]], 16, 36));

test("lv-heatmap", async ({ page }) => {
  await scene(page, "lv-heatmap", async () => {
    await page.goto(`${P}/simulation/heatmap/${IDS.asIsRun}`);
    await expect(page.getByText("Collo di bottiglia").first()).toBeVisible();
    await page.getByRole("button", { name: "Mostra tutta la tela" }).click();
  }, async (rec) => {
    tag(rec, "heat");
    await read(page, 1600);
    for (const id of ["send_request", "check_request", "approve_spend"]) {
      await moveTo(page, page.locator(`[data-element-id='${id}']`).first(), MOVE);
      await read(page, 900);
    }
    tag(rec, "bottleneck");
    await read(page, 600);
    await moveTo(page, page.getByText("Collo di bottiglia").first(), MOVE);
    await read(page, 2200);
    await moveTo(page, page.getByText(/Quota dell.attesa totale/).first(), MOVE);
    await read(page, 3000);
  });
});

// --- Solve: Results & Deliverables ------------------------------------------

test("lv-compare", async ({ page }) => {
  await scene(page, "lv-compare", async () => {
    await page.goto(`${P}/simulation/compare?a=${IDS.asIsRun}&b=${IDS.toBeRun}`);
    await expect(page.getByText(/attraversamento −/)).toBeVisible();
    await page.getByRole("button", { name: "Mostra tutta la tela" }).click();
  }, async (rec) => {
    tag(rec, "delta");
    await read(page, 1400);
    await moveTo(page, page.getByText(/attraversamento −/), MOVE);
    await read(page, 3200);
    for (const id of ["approve_spend", "issue_po"]) {
      await moveTo(page, page.locator(`[data-element-id='${id}']`).first(), MOVE);
      await read(page, 1200);
    }
    tag(rec, "note");
    await moveTo(page, page.getByText(/Per sapere se la differenza/).first(), MOVE);
    await read(page, 3000);
  });
});

test("lv-handover", async ({ page }) => {
  await scene(page, "lv-handover", async () => {
    await page.goto(P);
    await expect(page.getByRole("button", { name: /Consegna/ }).first()).toBeVisible();
  }, async (rec) => {
    tag(rec, "checks");
    await read(page, 1000);
    await clickOn(page, page.getByRole("button", { name: /Consegna/ }).first(), MOVE);
    await expect(page.getByText(/controlli superati/).first()).toBeVisible();
    await read(page, 1400);
    await moveTo(page, page.getByText(/controlli superati/).first(), MOVE);
    await read(page, 1400);
    for (const text of ["Supportato dalle fonti", "Simulazione eseguita"]) {
      await moveTo(page, page.getByText(text).first(), MOVE);
      await read(page, 1300);
    }
    tag(rec, "preview");
    await clickOn(page, page.getByRole("button", { name: /Anteprima per il cliente/ }).first(), MOVE);
    await read(page, 2600);
    const view = page.locator("main");
    await slowScroll(page, await scrollable(view), 520, 5200);
    await read(page, 1600);
    tag(rec, "done");
    await read(page, 3600);
  });
});

// --- Targhette, capitoli e disclaimer come PNG trasparenti ------------------

test("lv-overlays", async ({ page }) => {
  const dir = resolve(OUT, "overlays");
  mkdirSync(dir, { recursive: true });
  await page.goto("/home");
  await expect(page.getByText("Acquisti indiretti e servizi").first()).toBeVisible();
  const font = (await page.evaluate(() => getComputedStyle(document.body).fontFamily)).replace(/"/g, "'");
  const esc = (text: string) => text.replace(/&/g, "&amp;").replace(/</g, "&lt;");
  // Una pagina vuota con il font dell'app: ogni PNG e' ritagliato al suo contenuto.
  const render = async (name: string, body: string) => {
    await page.setContent(`<!doctype html><html><body style="margin:0;background:transparent;font-family:${font}"><div id="x" style="display:inline-block">${body}</div></body></html>`);
    await page.locator("#x").screenshot({ path: resolve(dir, `${name}.png`), omitBackground: true });
  };
  const index: Record<string, string> = {};
  for (const [sceneId, tags] of Object.entries(script.scenes)) {
    for (const [key, text] of Object.entries(tags as Record<string, { it: string; en: string }>)) {
      const name = `tag-${sceneId}-${key}`;
      index[name] = text.it;
      await render(name, `<div style="padding:12px 22px 13px;background:#0f172a;border-radius:14px;white-space:nowrap;box-shadow:0 10px 30px rgba(15,23,42,.25)">
        <div style="display:flex;gap:10px;align-items:baseline"><span style="flex:none;font-size:11px;font-weight:700;letter-spacing:.06em;color:#93c5fd">IT</span><span style="font-size:22px;font-weight:620;letter-spacing:-.01em;color:#fff;line-height:1.25">${esc(text.it)}</span></div>
        <div style="display:flex;gap:10px;align-items:baseline;margin-top:4px"><span style="flex:none;font-size:11px;font-weight:700;letter-spacing:.06em;color:#93c5fd">EN</span><span style="font-size:17px;font-weight:450;color:#cbd5e1;line-height:1.25">${esc(text.en)}</span></div></div>`);
    }
  }
  // Una riga sola e dentro la fascia libera fra capitolo e disclaimer.
  for (const name of Object.keys(index)) {
    const { width } = await page.evaluate(async (src) => {
      const image = new Image();
      image.src = src;
      await image.decode();
      return { width: image.naturalWidth };
    }, `data:image/png;base64,${readFileSync(resolve(dir, `${name}.png`)).toString("base64")}`);
    expect(width, `${name} troppo larga`).toBeLessThanOrEqual(840);
  }
  for (const [key, text] of Object.entries(script.chapters)) {
    await render(`chapter-${key}`, `<div style="display:inline-flex;align-items:center;gap:10px;padding:8px 14px;background:#fff;border:1px solid #dbe4f0;border-radius:999px;box-shadow:0 6px 18px rgba(15,23,42,.08)">
      <span style="width:8px;height:8px;border-radius:50%;background:#2563eb"></span><span style="font-size:15px;font-weight:650;color:#0f172a">${esc(text.it)}</span><span style="font-size:13px;color:#64748b">${esc(text.en)}</span></div>`);
  }
  await render("disclaimer", `<div style="font-size:12.5px;color:#64748b;text-align:right;line-height:1.35">${esc(script.disclaimer.it)}<br>${esc(script.disclaimer.en)}</div>`);
  writeFileSync(resolve(dir, "index.json"), JSON.stringify(index, null, 1));
});
