/**
 * Riprese dei video della landing sul caso semplice (una richiesta di acquisto),
 * in italiano e in inglese con la stessa sceneggiatura.
 *
 *   npx playwright test -c playwright.launch.config.ts simple/clips
 *   DELIR_CLIP_LANGS=it npx playwright test -c playwright.launch.config.ts simple/clips
 *
 * Sulla landing la clip e' larga circa 720 px: qui si registra a 1280x720 con
 * densita' 1,5 (fotogrammi 1920x1080, testi un terzo piu' grandi) e ogni
 * momento di lettura ha un'inquadratura stretta (`rec.focus`). Il montaggio
 * (`scripts/launch_media_edit.py`, tagli `simple-*` di storyboard.json) segue
 * quelle inquadrature con la camera. Niente attesa iniziale con il testo: sulla
 * landing il testo sta accanto alla clip.
 *
 * Il link del cliente si mostra con l'indirizzo dell'app in produzione
 * (`DELIR_SHARE_ORIGIN`), non con quello locale della ripresa.
 */
import { expect, test, type Locator, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { Recorder, clickOn, cue, installCursor, moveTo, slowScroll } from "../recorder";
import { SIMPLE_IDS as IDS, simpleCase, type Lang } from "./case";
import { installSimpleApi, unhandled } from "./mockApi";

const RAW = resolve(process.cwd(), "artifacts", "launch-media", "raw");
const P = `/projects/${IDS.project}/processes/${IDS.process}`;
const SHARE_ORIGIN = process.env.DELIR_SHARE_ORIGIN ?? "https://app.delir.it";
const LANGS = (process.env.DELIR_CLIP_LANGS ?? "it,en").split(",") as Lang[];

const L = {
  it: {
    sources: /^Fonti/, evidence: "Evidenze", evidencePanel: "Evidenze del disegno", conformant: "Il disegno coincide con le fonti",
    quoted: "Citati dalle fonti", verified: "citazione verificata", comparison: /CONFRONTO CON GLI ALTRI FILE/i, divergences: /Divergenze \(\d+\)/,
    decide: /^Decidi$/, toDecide: /Da decidere/, openAgent: "Apri agente DeliR", agent: "Agente di Review", agentInput: "Scrivi all’agente di Review",
    send: "Invia messaggio", resizeChat: "Ridimensiona chat DeliR", play: "Riproduci", showAll: "Mostra tutta la tela", speed: "Velocità",
    bottleneck: "Collo di bottiglia", workspace: "Workspace", workspaceTitle: "Workspace degli scenari", resizePanel: "Ridimensiona pannello di dettagli",
    createLink: "Crea solo il link", preview: "Anteprima per il cliente", checks: /controlli superati/, approved: /Approvato · In uso/,
    message: /Scrivi un messaggio/, stop: /Ferma/, reading: /Leggo le fonti/, answered: /te la chiedo/, reviewDone: /Da verificare con Laura Conti/,
    probability: /probabilità che sia migliore/, noTradeOff: /non c'è scambio da pagare/, overview: /^Panoramica$/,
    divergenceA: /Laura firma il martedì e il giovedì/, divergenceB: /entro un giorno lavorativo/, threshold: /Sopra quale importo/,
    proposal: "Un delegato firma ogni giorno quando Laura non c'è", openIssue: /Soglia di importo per la firma/, objective: /Capire perché una richiesta/,
    nextStep: /Validazione del To-Be con Laura Conti/, project: "Richieste di acquisto", bQuote: /quando è in sede/,
  },
  en: {
    sources: /^Sources/, evidence: "Evidence", evidencePanel: "Drawing evidence", conformant: "The diagram matches the sources",
    quoted: "Quoted by the sources", verified: "quote verified", comparison: /COMPARISON WITH OTHER FILES/i, divergences: /Divergences \(\d+\)/,
    decide: /^Decide$/, toDecide: /To decide/, openAgent: "Open DeliR agent", agent: "Review agent", agentInput: "Write to the Review agent",
    send: "Send message", resizeChat: "Resize DeliR chat", play: "Play", showAll: "Show entire canvas", speed: "Speed",
    bottleneck: "Bottleneck", workspace: "Workspace", workspaceTitle: "Scenario workspace", resizePanel: "Resize details panel",
    createLink: "Create the link only", preview: "Client preview", checks: /checks met/, approved: /Approved · In use/,
    message: /Write a message/, stop: /Stop/, reading: /Reading the collected sources/, answered: /ask you/, reviewDone: /To check with Laura Conti/,
    probability: /probability it is better/, noTradeOff: /no trade-off to pay/, overview: /^Overview$/,
    divergenceA: /Laura signs on Tuesdays and Thursdays/, divergenceB: /within one working day/, threshold: /Above what amount/,
    proposal: "A delegate signs every day when Laura is away", openIssue: /Amount threshold for sign-off/, objective: /Understand why a purchase request/,
    nextStep: /To-Be validation with Laura Conti/, project: "Purchase requests", bQuote: /when she is in the office/,
  },
} as const;

test.skip(Boolean(process.env.CI) && process.env.DELIR_LAUNCH_MEDIA !== "1", "Generatore di media: in CI con DELIR_LAUNCH_MEDIA=1");
test.use({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1.5 });

test.afterAll(() => {
  if (unhandled.size) console.warn("Richieste non coperte dal caso semplice:", [...unhandled].join(", "));
});

async function clip(page: Page, id: string, setup: () => Promise<void>, act: (rec: Recorder) => Promise<void>): Promise<void> {
  await setup();
  await page.waitForTimeout(500);
  const rec = new Recorder(page, resolve(RAW, id));
  await rec.start();
  // Un istante fermo: e' il fotogramma su cui il loop si richiude.
  await page.waitForTimeout(600);
  rec.mark("action");
  await act(rec);
  await rec.stop();
}

async function scrollable(container: Locator): Promise<Locator> {
  const index = await container.evaluate((root) => {
    const all = [root, ...Array.from(root.querySelectorAll("*"))] as HTMLElement[];
    return all.findIndex((el) => el.scrollHeight > el.clientHeight + 40 && /(auto|scroll)/.test(getComputedStyle(el).overflowY));
  });
  return index <= 0 ? container : container.locator("*").nth(index - 1);
}

/** Porta `target` vicino alla cima del suo contenitore che scorre, lentamente. */
async function scrollTo(page: Page, target: Locator, ms: number, margin = 24): Promise<void> {
  const handle = await target.evaluateHandle((el) => {
    let node: HTMLElement | null = el.parentElement;
    while (node && !(node.scrollHeight > node.clientHeight + 40 && /(auto|scroll)/.test(getComputedStyle(node).overflowY))) node = node.parentElement;
    return node ?? document.scrollingElement ?? document.documentElement;
  });
  const delta = await target.evaluate((el, margin) => {
    let node: HTMLElement | null = el.parentElement;
    while (node && !(node.scrollHeight > node.clientHeight + 40 && /(auto|scroll)/.test(getComputedStyle(node).overflowY))) node = node.parentElement;
    const top = node ? node.getBoundingClientRect().top : 0;
    return el.getBoundingClientRect().top - top - margin;
  }, margin);
  const steps = Math.max(1, Math.round(ms / 50));
  for (let i = 0; i < steps && Math.abs(delta) > 4; i++) {
    await handle.evaluate((el, dy) => (el as HTMLElement).scrollBy({ top: dy }), delta / steps);
    await page.waitForTimeout(50);
  }
}

/** Scrive come una persona: si vede il testo comparire. */
async function typeLikeHuman(page: Page, box: Locator, text: string): Promise<void> {
  await clickOn(page, box, 600);
  const started = Date.now();
  await box.pressSequentially(text, { delay: 22 });
  cue("type", { count: text.length, length: (Date.now() - started) / 1000 }, (started - Date.now()) / 1000);
  await page.waitForTimeout(300);
}

for (const lang of LANGS) {
  const t = L[lang];
  const demo = simpleCase(lang);
  const id = (name: string) => `s-${lang}-${name}`;
  const task = (page: Page, node: string) => page.locator(`[data-element-id='${node}']`).first();

  test.describe(lang, () => {
    test.beforeEach(async ({ page }) => {
      page.setDefaultTimeout(10_000);
      await installSimpleApi(page, demo);
      await installCursor(page);
      // Solo nelle riprese: il marchio del renderer BPMN fuori dal fotogramma
      // (DELIR_SHOW_BPMN_WATERMARK=1 lo lascia). Il prodotto non cambia.
      if (process.env.DELIR_SHOW_BPMN_WATERMARK !== "1") {
        await page.addInitScript(() => {
          const style = document.createElement("style");
          style.textContent = ".bjs-powered-by, .bjs-powered-by-lightbox { display: none !important; }";
          document.addEventListener("DOMContentLoaded", () => document.head.append(style));
        });
      }
    });

    // 1. Le fonti del cliente: ogni affermazione con la sua frase esatta.
    test(id("fonti"), async ({ page }) => {
      await clip(page, id("fonti"), async () => {
        await page.goto(`/projects/${IDS.project}`);
        await page.getByRole("tab", { name: t.sources }).click();
        await expect(page.getByText(demo.sources[1].name).first()).toBeVisible();
      }, async (rec) => {
        await rec.focus(page.getByText(demo.sources[0].name).first().locator("xpath=ancestor::*[self::ul or self::ol or self::table or @role='list'][1]"), 1.6, 40);
        await moveTo(page, page.getByText(demo.sources[0].name).first(), 700);
        await page.waitForTimeout(700);
        await clickOn(page, page.getByText(demo.sources[1].name).first());
        const dialog = page.getByRole("dialog");
        const verified = dialog.getByText(t.verified).first();
        await expect(verified).toBeVisible();
        await page.waitForTimeout(300);
        await rec.focus(dialog, 1.45, 8);
        await moveTo(page, verified, 800);
        await page.waitForTimeout(1200);
        await slowScroll(page, await scrollable(dialog), 300, 3200);
        await page.waitForTimeout(1500);
        rec.wide();
        await page.waitForTimeout(700);
      });
    });

    // 2. La discussione con DeliR: legge le fonti e costruisce l'As-Is.
    test(id("discovery"), async ({ page }) => {
      await clip(page, id("discovery"), async () => {
        await page.goto(P);
        await expect(page.getByPlaceholder(t.message)).toBeVisible();
      }, async (rec) => {
        const box = page.getByPlaceholder(t.message);
        await rec.focus(box, 1.7, 40);
        await typeLikeHuman(page, box, demo.discoveryQuestion);
        await page.keyboard.press("Enter");
        rec.mark("sent");
        await rec.focus({ x: 150, y: 90, width: 980, height: 470 }, 1.35, 0);
        await moveTo(page, { x: 1100, y: 690 }, 600);
        await expect(page.getByText(t.reading).first()).toBeVisible({ timeout: 10_000 });
        await expect(page.getByRole("button", { name: t.stop })).toBeHidden({ timeout: 40_000 });
        rec.mark("answered");
        await page.waitForTimeout(2200);
        rec.wide();
        await page.waitForTimeout(600);
      });
    });

    // 3. L'As-Is con le evidenze: ogni attivita' ha la sua fonte.
    test(id("evidenze"), async ({ page }) => {
      await clip(page, id("evidenze"), async () => {
        await page.goto(`${P}?view=canvas`);
        await expect(task(page, "approve_spend")).toBeVisible();
      }, async (rec) => {
        await page.waitForTimeout(600);
        await clickOn(page, page.getByRole("button", { name: t.evidence }).first());
        const panel = page.getByRole("complementary", { name: t.evidencePanel });
        await expect(panel).toContainText("100%");
        await rec.focus(panel.getByText(t.conformant).first(), 2.0, 110);
        await moveTo(page, panel.getByText(t.conformant).first(), 800);
        await page.waitForTimeout(1500);
        await clickOn(page, panel.locator("summary", { hasText: t.quoted }));
        const quote = panel.getByText(t.bQuote).first();
        await quote.scrollIntoViewIfNeeded();
        await page.waitForTimeout(300);
        await rec.focus(quote, 2.1, 80);
        await moveTo(page, quote, 900);
        await page.waitForTimeout(2400);
        rec.wide();
        await page.waitForTimeout(300);
        await rec.focus(task(page, "approve_spend"), 2.2, 120);
        await moveTo(page, task(page, "approve_spend"), 900);
        await page.waitForTimeout(1500);
        rec.wide();
        await page.waitForTimeout(800);
      });
    });

    // 4. Le versioni che non tornano: la procedura contro chi ci lavora.
    test(id("divergenze"), async ({ page }) => {
      await clip(page, id("divergenze"), async () => {
        await page.goto(`/projects/${IDS.project}`);
        await page.getByRole("tab", { name: t.sources }).click();
        await expect(page.getByText(demo.sources[1].name).first()).toBeVisible();
      }, async (rec) => {
        await clickOn(page, page.getByText(demo.sources[1].name).first());
        const dialog = page.getByRole("dialog");
        await expect(dialog.getByText(t.divergences).first()).toBeAttached();
        await page.waitForTimeout(500);
        await scrollTo(page, dialog.getByText(t.comparison).first(), 2000);
        await page.waitForTimeout(300);
        await rec.focus(dialog.getByText(t.divergences).first(), 1.9, 150);
        await moveTo(page, dialog.getByText(t.divergences).first(), 700);
        await page.waitForTimeout(700);
        const a = dialog.getByText(t.divergenceA).last();
        await rec.focus(a, 2.1, 80);
        await moveTo(page, a, 900);
        await page.waitForTimeout(1700);
        const b = dialog.getByText(t.divergenceB).last();
        await rec.focus(b, 2.1, 80);
        await moveTo(page, b, 900);
        await page.waitForTimeout(2200);
        rec.wide();
        await page.waitForTimeout(700);
      });
    });

    // 5. Quello che nessuno dice diventa una domanda per il cliente.
    test(id("lacuna"), async ({ page }) => {
      await clip(page, id("lacuna"), async () => {
        await page.goto(P);
        await expect(page.getByRole("button", { name: t.decide })).toBeVisible();
      }, async (rec) => {
        await clickOn(page, page.getByRole("button", { name: t.decide }));
        await page.waitForTimeout(700);
        await clickOn(page, page.getByRole("button", { name: t.toDecide }));
        await page.waitForTimeout(600);
        const question = page.getByText(t.threshold).first();
        await rec.focus(question, 2.1, 130);
        await moveTo(page, question, 900);
        await page.waitForTimeout(2200);
        const option = page.getByText(demo.review.open_questions[0].options[0].label).first();
        await rec.focus(option, 2.1, 130);
        await moveTo(page, option, 800);
        await page.waitForTimeout(2300);
        rec.wide();
        await page.waitForTimeout(700);
      });
    });

    // 6. Review con DeliR su "Autorizza la spesa": la proposta, con le fonti.
    test(id("review"), async ({ page }) => {
      await clip(page, id("review"), async () => {
        await page.goto(`${P}?view=review`);
        await expect(page.locator(".review-canvas [data-element-id='approve_spend']").first()).toBeVisible();
      }, async (rec) => {
        const node = page.locator(".review-canvas [data-element-id='approve_spend']").first();
        await rec.focus(node, 2.0, 160);
        await clickOn(page, node, 900);
        await page.waitForTimeout(900);
        rec.wide();
        await clickOn(page, page.getByRole("button", { name: t.openAgent, exact: true }));
        const chat = page.getByRole("dialog", { name: t.agent });
        await expect(chat).toBeVisible();
        const handle = page.getByRole("button", { name: t.resizeChat });
        await handle.focus();
        for (let step = 0; step < 14; step += 1) await page.keyboard.press(step % 2 ? "ArrowLeft" : "ArrowUp");
        for (let step = 0; step < 6; step += 1) await page.keyboard.press("ArrowUp");
        await page.waitForTimeout(200);
        await rec.focus(chat, 1.4, 20);
        await typeLikeHuman(page, page.getByLabel(t.agentInput), demo.reviewQuestion);
        await clickOn(page, page.getByRole("button", { name: t.send, exact: true }), 400);
        rec.mark("sent");
        await expect(chat.getByText(t.reviewDone).first()).toBeVisible({ timeout: 30_000 });
        rec.mark("answered");
        await page.waitForTimeout(700);
        const log = await scrollable(chat);
        const height = await log.evaluate((el) => el.scrollTop);
        if (height > 0) {
          await slowScroll(page, log, -height, 1200);
          await page.waitForTimeout(1000);
          await slowScroll(page, log, height, 2600);
        }
        await page.waitForTimeout(1500);
        rec.wide();
        await page.waitForTimeout(500);
      });
    });

    // 7. Il replay dell'As-Is: le richieste si fermano in attesa della firma.
    for (const [name, run] of [["replay-as-is", IDS.asIsRun], ["replay-to-be", IDS.toBeRun]] as const) {
      test(id(name), async ({ page }) => {
        await clip(page, id(name), async () => {
          await page.goto(`${P}/simulation/replay/${run}`);
          await expect(page.getByRole("button", { name: t.play, exact: true })).toBeVisible();
          await page.getByRole("button", { name: t.showAll }).click();
          await page.getByRole("combobox", { name: t.speed }).click();
          await page.getByRole("option").filter({ hasText: "40 s" }).first().click();
          await page.waitForTimeout(800);
        }, async (rec) => {
          // Il processo riempie l'inquadratura: si vedono le richieste che avanzano e dove si fermano.
          const diagram = page.locator(".djs-container").first();
          await rec.focus(diagram, 1.5, 6);
          await clickOn(page, page.getByRole("button", { name: t.play, exact: true }), 600);
          await moveTo(page, { x: 640, y: 700 }, 500);
          await page.waitForTimeout(3800);
          await rec.focus(task(page, "approve_spend"), 2.0, 200);
          await page.waitForTimeout(3600);
          await rec.focus(diagram, 1.5, 6);
          await page.waitForTimeout(3000);
        });
      });
    }

    // 8. La heatmap: il collo di bottiglia, misurato.
    test(id("heatmap"), async ({ page }) => {
      await clip(page, id("heatmap"), async () => {
        await page.goto(`${P}/simulation/heatmap/${IDS.asIsRun}`);
        await expect(page.getByText(t.bottleneck).first()).toBeVisible();
        await page.getByRole("button", { name: t.showAll }).click();
        await page.waitForTimeout(600);
      }, async (rec) => {
        await rec.focus(page.locator(".djs-container").first(), 1.5, 6);
        await page.waitForTimeout(1400);
        await rec.focus(task(page, "approve_spend"), 2.2, 160);
        await moveTo(page, task(page, "approve_spend"), 1000);
        await page.waitForTimeout(1600);
        const tag = page.getByText(t.bottleneck).first();
        await rec.focus(tag.locator("xpath=ancestor::*[self::section or self::article or self::div][2]"), 1.8, 20);
        await moveTo(page, tag, 900);
        await page.waitForTimeout(2600);
        rec.wide();
        await page.waitForTimeout(700);
      });
    });

    // 9. Gli scenari a confronto, ripetuti, e il decision record da consegnare.
    test(id("workspace"), async ({ page }) => {
      await clip(page, id("workspace"), async () => {
        await page.goto(`${P}/simulation`);
        await page.getByRole("button", { name: t.workspace, exact: true }).click();
        await expect(page.getByText(t.workspaceTitle)).toBeVisible();
        const handle = page.getByRole("separator", { name: t.resizePanel });
        const box = await handle.boundingBox();
        if (box) {
          await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
          await page.mouse.down();
          await page.mouse.move(300, box.y + box.height / 2, { steps: 8 });
          await page.mouse.up();
        }
        await page.waitForTimeout(400);
      }, async (rec) => {
        const scenarioB = page.getByText(demo.workspace.alternatives[1].name).first();
        await scrollTo(page, scenarioB, 1600, 50);
        await page.waitForTimeout(300);
        await rec.focus(scenarioB.locator("xpath=ancestor::tr[1]"), 1.6, 16);
        await moveTo(page, page.getByText(t.probability).last(), 900);
        await page.waitForTimeout(2200);
        const reading = page.getByText(t.noTradeOff).first();
        if (await reading.count()) {
          await scrollTo(page, reading, 1400, 140);
          await rec.focus(reading, 1.9, 70);
          await moveTo(page, reading, 900);
          await page.waitForTimeout(2400);
        }
        rec.wide();
        await scrollTo(page, scenarioB, 1000, 50);
        const recordButton = page.locator("[data-sim-decision-record]").last();
        const [download] = await Promise.all([page.waitForEvent("download"), clickOn(page, recordButton, 800)]);
        const html = readFileSync((await download.path())!, "utf-8");
        await page.setContent(html);
        await page.evaluate(() => { document.body.style.zoom = "1.2"; });
        await page.waitForTimeout(500);
        await rec.focus({ x: 260, y: 0, width: 760, height: 428 }, 1.68, 0);
        await page.waitForTimeout(1500);
        await slowScroll(page, page.locator("html"), 380, 2400);
        await page.waitForTimeout(2200);
        rec.wide();
        await page.waitForTimeout(700);
      });
    });

    // 10. La consegna: controlli, cosa cambia e perche', il link per il cliente.
    test(id("consegna"), async ({ page }) => {
      await clip(page, id("consegna"), async () => {
        await page.goto(`${P}/handover`);
        await expect(page.getByText(t.checks)).toBeVisible();
      }, async (rec) => {
        const checks = page.getByText(t.checks);
        await rec.focus(checks.locator("xpath=ancestor::*[self::section or self::div][2]"), 1.5, 10);
        await moveTo(page, checks, 800);
        await page.waitForTimeout(1500);
        rec.wide();
        const change = page.getByText(t.proposal).first();
        await scrollTo(page, change, 2000, 90);
        await page.waitForTimeout(300);
        await rec.focus(change.locator("xpath=ancestor::*[self::article or self::li or self::div][1]"), 1.7, 30);
        await moveTo(page, change, 900);
        await page.waitForTimeout(2600);
        rec.wide();
        await scrollTo(page, page.getByText(t.checks), 1000, 300);
        await page.waitForTimeout(300);
        const create = page.getByRole("button", { name: t.createLink });
        await rec.focus(create.locator("xpath=ancestor::section[1]"), 1.7, 20);
        await clickOn(page, create, 800);
        await page.waitForTimeout(300);
        if (SHARE_ORIGIN) {
          // L'indirizzo dell'app in produzione al posto di quello locale della ripresa.
          await page.locator("input[readonly], input").evaluateAll((inputs, origin) => {
            for (const input of inputs as HTMLInputElement[]) {
              if (input.value.includes("/share.html#")) input.value = input.value.replace(/^https?:\/\/[^/]+/, origin);
            }
          }, SHARE_ORIGIN);
        }
        await page.waitForTimeout(1800);
        rec.wide();
        await clickOn(page, page.getByRole("button", { name: t.preview }));
        await expect(page.getByText(t.approved).first()).toBeVisible();
        await page.waitForTimeout(400);
        await rec.focus(page.getByText(t.approved).first().locator("xpath=ancestor::*[self::section or self::div][1]"), 1.6, 40);
        await page.waitForTimeout(1800);
        rec.wide();
        await slowScroll(page, page.locator("html"), 500, 2200);
        await page.waitForTimeout(900);
      });
    });

    // 11. Il contesto dell'incarico: obiettivo, avanzamento, punti aperti.
    test(id("contesto"), async ({ page }) => {
      await clip(page, id("contesto"), async () => {
        await page.goto("/home");
        await expect(page.getByText(demo.client).first()).toBeVisible();
      }, async (rec) => {
        await clickOn(page, page.getByText(t.project).first());
        await expect(page.getByRole("tab", { name: t.sources })).toBeVisible();
        await page.waitForTimeout(800);
        const objective = page.getByText(t.objective).first();
        await rec.focus(objective, 1.8, 90);
        await moveTo(page, objective, 900);
        await page.waitForTimeout(1800);
        const milestone = page.getByText(demo.project.milestones[2].title).first();
        await rec.focus(milestone, 1.9, 140);
        await moveTo(page, milestone, 900);
        await page.waitForTimeout(1700);
        const issue = page.getByText(t.openIssue).first();
        if (await issue.count()) {
          await scrollTo(page, issue, 1400, 200);
          await rec.focus(issue, 1.9, 120);
          await moveTo(page, issue, 900);
          await page.waitForTimeout(1800);
        }
        rec.wide();
        await page.waitForTimeout(800);
      });
    });
  });
}

// Il disclaimer delle clip, nelle due lingue (lo sovrappone il montaggio).
test("overlays simple", async ({ page }) => {
  const demo = simpleCase("it");
  await installSimpleApi(page, demo);
  await page.goto("/home");
  await expect(page.getByText(demo.client).first()).toBeVisible();
  const font = (await page.evaluate(() => getComputedStyle(document.body).fontFamily)).replace(/"/g, "'");
  await page.setViewportSize({ width: 1920, height: 1080 });
  const texts = { it: "Azienda, persone e valori dimostrativi · simulazione", en: "Fictional company, people and values · simulation" };
  for (const [lang, text] of Object.entries(texts)) {
    await page.setContent(`<!doctype html><html><body style="margin:0;background:transparent;font-family:${font}">
      <div style="position:fixed;right:22px;bottom:16px;font-size:20px;color:#475569;background:rgba(255,255,255,.94);border:1px solid #e2e8f0;border-radius:999px;padding:6px 16px">${text}</div></body></html>`);
    await page.screenshot({ path: resolve(process.cwd(), "artifacts", "launch-media", "overlays", `disclaimer-simple-${lang}.png`), omitBackground: true });
  }
});
