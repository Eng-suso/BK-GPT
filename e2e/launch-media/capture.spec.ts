/**
 * Media di lancio di DeliR: scene del video muto, screenshot e card per la landing.
 *
 *   npm run media:launch            # cattura + montaggio
 *
 * Ogni scena e' un test: prepara la pagina, poi registra (Recorder) mentre il
 * cursore fa i gesti del consulente. I primi `hold` secondi la pagina resta
 * ferma: e' il tempo in cui il montaggio mostra il testo della scena (prima il
 * testo, poi l'azione). I testi stanno in storyboard.json.
 */
import { expect, test, type Locator, type Page } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";

import {
  AS_IS_REVIEW_NODE,
  IDS,
  PROCESS_OWNER,
  REVIEW_NODE,
  asIsReviewQuestion,
  discoveryQuestion,
  reviewQuestion,
} from "./demo";
import { installDemoApi, unhandled } from "./mockApi";
import { Recorder, clickOn, cue, installCursor, moveTo, slowScroll } from "./recorder";
import storyboard from "./storyboard.json";

const OUT = resolve(process.cwd(), "artifacts", "launch-media");
const RAW = resolve(OUT, "raw");
const P = `/projects/${IDS.project}/processes/${IDS.process}`;
const HOLD = storyboard.hold * 1000;

test.skip(Boolean(process.env.CI) && process.env.DELIR_LAUNCH_MEDIA !== "1", "Generatore di media: in CI con DELIR_LAUNCH_MEDIA=1");

test.beforeEach(async ({ page }, info) => {
  page.setDefaultTimeout(10_000);
  // La discussione parte vuota solo dove il consulente la apre davanti a noi.
  await installDemoApi(page, "it", { live: info.title === "02-interviste-a-delir" });
  await installCursor(page);
});

test.afterAll(() => {
  if (unhandled.size) console.warn("Richieste non coperte dal caso demo:", [...unhandled].join(", "));
});

async function scene(page: Page, id: string, setup: () => Promise<void>, act: (rec: Recorder) => Promise<void>): Promise<void> {
  await setup();
  await page.waitForTimeout(600);
  const rec = new Recorder(page, resolve(RAW, id));
  await rec.start();
  await page.waitForTimeout(HOLD);
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

async function openSources(page: Page): Promise<void> {
  await page.goto(`/projects/${IDS.project}`);
  await expect(page.getByRole("tab", { name: /Fonti/ })).toBeVisible();
}

// --- Card: HTML dentro l'app, cosi' i caratteri sono i suoi.

type Hook = { line: string; sub?: string; quote?: string };
type CardKind = "hook" | "promise" | "result" | "close";
type CardScene = { title?: string; points?: string[]; tiles?: { value: string; label: string }[]; note?: string };

/**
 * Gancio: i problemi del consulente, uno per volta (una card sostituisce
 * l'altra). Promessa: cosa porta al cliente. Risultato: i numeri del caso.
 * Chiusura: il marchio con l'esito.
 */
async function showCard(page: Page, id: string, kind: CardKind, step: number): Promise<void> {
  await page.goto("/home");
  await expect(page.getByText("Acquisti indiretti e servizi").first()).toBeVisible();
  const item = storyboard.scenes.find((entry) => entry.id === id) as CardScene;
  await page.evaluate(({ kind, hook, item, disclaimer, step }) => {
    const css = `
      .launch-card { position: fixed; inset: 0; z-index: 2147483000; display: grid; place-items: center; background: #f8fafc; color: #0f172a; }
      .launch-card .beat { position: absolute; display: grid; gap: 24px; justify-items: center; text-align: center; width: 1500px;
        opacity: 0; transform: translateY(18px); animation: launch-in 600ms cubic-bezier(.22,1,.36,1) forwards, launch-out 400ms ease-in forwards; }
      .launch-card .beat:last-of-type { animation: launch-in 600ms cubic-bezier(.22,1,.36,1) forwards; }
      .launch-card .line { font-size: 78px; font-weight: 650; letter-spacing: -0.03em; line-height: 1.12; }
      .launch-card .quote { font-size: 78px; font-weight: 650; letter-spacing: -0.03em; color: #1d4ed8; }
      .launch-card .sub { font-size: 42px; color: #64748b; }
      .launch-card .in { opacity: 0; transform: translateY(16px); animation: launch-in 700ms cubic-bezier(.22,1,.36,1) forwards; }
      .launch-card .head { font-size: 54px; font-weight: 650; letter-spacing: -0.02em; margin-bottom: 18px; }
      .launch-card .points { display: grid; gap: 22px; width: 1250px; }
      .launch-card .point { display: flex; align-items: center; gap: 26px; font-size: 50px; font-weight: 550; letter-spacing: -0.02em;
        background: #fff; border: 1px solid #e2e8f0; border-radius: 22px; padding: 26px 34px; box-shadow: 0 12px 34px rgba(15,23,42,.07); }
      .launch-card .tick { flex: none; display: grid; place-items: center; width: 54px; height: 54px; border-radius: 50%; background: #16a34a; color: #fff; font-size: 32px; }
      .launch-card .tiles { display: grid; grid-template-columns: repeat(4, 360px); gap: 24px; }
      .launch-card .tile { background: #fff; border: 1px solid #e2e8f0; border-radius: 24px; padding: 34px 30px; text-align: left; box-shadow: 0 12px 34px rgba(15,23,42,.07); }
      .launch-card .tile b { display: block; font-size: 76px; letter-spacing: -0.03em; color: #1d4ed8; }
      .launch-card .tile span { display: block; margin-top: 10px; font-size: 26px; line-height: 1.3; color: #475569; }
      .launch-card .note { margin-top: 26px; font-size: 24px; color: #64748b; text-align: center; }
      .launch-card h1 { opacity: 0; animation: launch-in 800ms cubic-bezier(.22,1,.36,1) forwards; font-size: 62px; letter-spacing: -0.03em; margin: 26px 0 0; text-align: center; max-width: 1500px; }
      .launch-card .brand { opacity: 0; animation: launch-in 900ms cubic-bezier(.22,1,.36,1) forwards; font-size: 120px; font-weight: 700; color: #1d4ed8; letter-spacing: -0.04em; text-align: center; }
      .launch-card .disclaimer { position: fixed; right: 36px; bottom: 28px; font-size: 16px; color: #94a3b8; }
      .launch-card.paused * { animation-play-state: paused !important; }
      @keyframes launch-in { to { opacity: 1; transform: none; } }
      @keyframes launch-out { to { opacity: 0; transform: translateY(-14px); } }`;
    const el = (tag: string, className: string, text?: string, delay?: number) => {
      const node = document.createElement(tag);
      node.className = className;
      if (text !== undefined) node.textContent = text;
      if (delay !== undefined) node.style.animationDelay = `${delay}s`;
      return node;
    };
    const root = el("div", "launch-card paused");
    const style = document.createElement("style");
    style.textContent = css;
    root.append(style);
    if (kind === "hook") {
      hook.forEach((entry, index) => {
        const beat = el("div", "beat");
        const at = 0.2 + index * step;
        // Entra a `at`, esce poco prima che entri il problema dopo.
        beat.style.animationDelay = `${at}s, ${at + step - 0.45}s`;
        beat.append(el("div", "line", entry.line));
        if (entry.quote) beat.append(el("div", "quote", `«${entry.quote}»`));
        if (entry.sub) beat.append(el("div", "sub", entry.sub));
        root.append(beat);
      });
    } else if (kind === "promise") {
      const wrap = el("div", "");
      wrap.append(el("div", "head in", item.title, 0.2));
      const points = el("div", "points");
      (item.points ?? []).forEach((text, index) => {
        const point = el("div", "point in", undefined, 0.9 + index * 0.9);
        point.append(el("span", "tick", "✓"), el("span", "", text));
        points.append(point);
      });
      wrap.append(points);
      root.append(wrap);
    } else if (kind === "result") {
      const wrap = el("div", "");
      wrap.append(el("div", "head in", item.title, 0.2));
      const tiles = el("div", "tiles");
      (item.tiles ?? []).forEach((tile, index) => {
        const box = el("div", "tile in", undefined, 0.8 + index * 0.6);
        box.append(el("b", "", tile.value), el("span", "", tile.label));
        tiles.append(box);
      });
      wrap.append(tiles, el("div", "note in", item.note, 3.4));
      root.append(wrap);
    } else {
      const wrap = el("div", "");
      wrap.append(el("div", "brand", "DeliR", 0.3), el("h1", "", item.title ?? "", 1.1));
      root.append(wrap);
    }
    root.append(el("div", "disclaimer", disclaimer));
    document.body.append(root);
    document.getElementById("launch-cursor")?.remove();
  }, { kind, hook: storyboard.hook as Hook[], item, disclaimer: storyboard.disclaimer, step });
}

const HOOK_STEP = 2.6;

async function cardScene(page: Page, id: string, kind: CardKind, seconds: number): Promise<void> {
  await showCard(page, id, kind, HOOK_STEP);
  const rec = new Recorder(page, resolve(RAW, id));
  await rec.start();
  await page.evaluate(() => document.querySelector(".launch-card")?.classList.remove("paused"));
  // Gli istanti delle animazioni CSS delle card (vedi showCard).
  const item = storyboard.scenes.find((entry) => entry.id === id) as CardScene;
  if (kind === "hook") storyboard.hook.forEach((_, index) => cue("beat", {}, 0.2 + index * HOOK_STEP));
  if (kind === "promise") (item.points ?? []).forEach((_, index) => cue("reveal", {}, 0.9 + index * 0.9));
  if (kind === "result") (item.tiles ?? []).forEach((_, index) => cue("reveal", {}, 0.8 + index * 0.6));
  if (kind === "close") cue("logo", {}, 0.3);
  await page.waitForTimeout(seconds * 1000);
  await rec.stop();
}

test("01-gancio", async ({ page }) => cardScene(page, "01-gancio", "hook", 0.4 + storyboard.hook.length * HOOK_STEP));
test("01b-promessa", async ({ page }) => cardScene(page, "01b-promessa", "promise", 5.6));
test("17b-risultato", async ({ page }) => cardScene(page, "17b-risultato", "result", 6.4));
test("18-chiusura", async ({ page }) => cardScene(page, "18-chiusura", "close", 5));

// --- Chat con DeliR ----------------------------------------------------------

/** Scrive come una persona: si vede il testo comparire, poi invia. */
async function typeLikeHuman(page: Page, box: Locator, text: string): Promise<void> {
  await clickOn(page, box, 600);
  const started = Date.now();
  await box.pressSequentially(text, { delay: 28 });
  // La digitazione, come intervallo: il montaggio la rende con i tasti.
  cue("type", { count: text.length, length: (Date.now() - started) / 1000 }, (started - Date.now()) / 1000);
  await page.waitForTimeout(350);
}

/** Apre la Review di un task del modello e il suo agente. */
async function openReviewAgent(page: Page, rec: Recorder, taskName: string, node: string): Promise<Locator> {
  await clickOn(page, page.getByRole("button", { name: /^Task \d+$/ }).first());
  await page.waitForTimeout(300);
  await clickOn(page, page.getByRole("button", { name: taskName, exact: true }));
  // La camera va sul task scelto: monte e valle evidenziati.
  await rec.focus(page.locator(`.review-canvas [data-element-id='${node}']`).first(), 1.7, 220);
  await page.waitForTimeout(1500);
  rec.wide();
  await clickOn(page, page.getByRole("button", { name: "Apri agente DeliR", exact: true }));
  const chat = page.getByRole("dialog", { name: "Agente di Review" });
  await expect(chat).toBeVisible();
  // Piu' spazio alla conversazione: la si legge per intero.
  const handle = page.getByRole("button", { name: "Ridimensiona chat DeliR" });
  await moveTo(page, handle, 500);
  await handle.focus();
  for (let step = 0; step < 14; step += 1) {
    await page.keyboard.press(step % 2 ? "ArrowLeft" : "ArrowUp");
    await page.waitForTimeout(25);
  }
  for (let step = 0; step < 6; step += 1) await page.keyboard.press("ArrowUp");
  await page.waitForTimeout(200);
  await rec.focus(chat, 1.4, 24);
  return chat;
}

async function askReview(page: Page, rec: Recorder, chat: Locator, question: string, done: RegExp): Promise<void> {
  await typeLikeHuman(page, page.getByLabel("Scrivi all’agente di Review"), question);
  await clickOn(page, page.getByRole("button", { name: "Invia messaggio", exact: true }), 400);
  rec.mark("sent");
  await moveTo(page, chat.getByText(question).first(), 500);
  await expect(chat.getByText(done).first()).toBeVisible({ timeout: 30_000 });
  rec.mark("answered");
  // La risposta e' piu' lunga del pannello: si torna all'inizio e la si rilegge.
  await page.waitForTimeout(700);
  const log = await scrollable(chat);
  const height = await log.evaluate((el) => el.scrollTop);
  if (height > 0) {
    await slowScroll(page, log, -height, 1400);
    await page.waitForTimeout(1200);
    await slowScroll(page, log, height, 2600);
  }
}


/**
 * Le chat si leggono solo da vicino: 1280x720 a densita' 1,5, cioe' fotogrammi
 * a 1920x1080 con i testi un terzo piu' grandi.
 */
test.describe("chat ravvicinate", () => {
  test.use({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1.5 });

  test("02-interviste-a-delir", async ({ page }) => {
    await scene(page, "02-interviste-a-delir", async () => {
      await page.goto(P);
      await expect(page.getByPlaceholder(/Scrivi un messaggio/)).toBeVisible();
    }, async (rec) => {
      const box = page.getByPlaceholder(/Scrivi un messaggio/);
      await rec.focus(box, 1.6, 40);
      await typeLikeHuman(page, box, discoveryQuestion);
      await page.keyboard.press("Enter");
      rec.mark("sent");
      // La conversazione: la domanda, le fasi di lavoro, la risposta.
      await rec.focus({ x: 170, y: 110, width: 940, height: 420 }, 1.35, 0);
      await moveTo(page, { x: 1100, y: 690 }, 600);
      await expect(page.getByText(/Leggo le fonti raccolte/).first()).toBeVisible({ timeout: 10_000 });
      // La risposta e' completa quando torna il pulsante di invio al posto di "Ferma".
      await expect(page.getByRole("button", { name: /Ferma/ })).toBeHidden({ timeout: 40_000 });
      rec.mark("answered");
      await page.waitForTimeout(1600);
    });
  });

  test("07-review-as-is", async ({ page }) => {
    await scene(page, "07-review-as-is", async () => {
      await page.goto(`${P}?view=review`);
      await expect(page.locator(`.review-canvas [data-element-id='${AS_IS_REVIEW_NODE}']`).first()).toBeVisible();
    }, async (rec) => {
      const chat = await openReviewAgent(page, rec, "Regolarizza ordine a posteriori", AS_IS_REVIEW_NODE);
      await askReview(page, rec, chat, asIsReviewQuestion, /Da confermare con Laura Conti/);
      await page.waitForTimeout(600);
      rec.wide();
      await page.waitForTimeout(1200);
    });
  });

  test("12-review-to-be", async ({ page }) => {
    await scene(page, "12-review-to-be", async () => {
      await page.goto(`${P}?view=review`);
      await expect(page.locator(`.review-canvas [data-element-id='${REVIEW_NODE}']`).first()).toBeVisible();
    }, async (rec) => {
      const chat = await openReviewAgent(page, rec, "Autorizza spesa", REVIEW_NODE);
      await askReview(page, rec, chat, reviewQuestion, /Da verificare con Laura Conti/);
      await page.waitForTimeout(900);
      await moveTo(page, page.getByRole("button", { name: "Salva come ipotesi" }), 800);
      await page.waitForTimeout(1500);
    });
  });
});

// --- Scene di prodotto -----------------------------------------------------

test("03-fonti", async ({ page }) => {
  await scene(page, "03-fonti", () => openSources(page), async (rec) => {
    await clickOn(page, page.getByRole("tab", { name: /Fonti/ }));
    await page.waitForTimeout(900);
    await clickOn(page, page.getByText("Intervista Laura Conti").first());
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByText("citazione verificata").first()).toBeVisible();
    await page.waitForTimeout(500);
    await rec.focus(dialog, 1.35, 16);
    await page.waitForTimeout(340);
    await moveTo(page, dialog.getByText("citazione verificata").first(), 800);
    await slowScroll(page, await scrollable(dialog), 520, 4200);
    await page.waitForTimeout(840);
  });
});

test("04-passaggio-nascosto", async ({ page }) => {
  await scene(page, "04-passaggio-nascosto", async () => {
    await openSources(page);
    await page.getByRole("tab", { name: /Fonti/ }).click();
    await expect(page.getByText("Intervista Francesca Neri").first()).toBeVisible();
  }, async (rec) => {
    await clickOn(page, page.getByText("Intervista Francesca Neri").first());
    const dialog = page.getByRole("dialog");
    const section = dialog.getByText(/CONFRONTO CON GLI ALTRI FILE/i).first();
    await expect(dialog.getByText("Divergenze (3)").first()).toBeAttached();
    await page.waitForTimeout(800);
    const box = await scrollable(dialog);
    const offset = await section.evaluate((el) => {
      let node: HTMLElement | null = el as HTMLElement;
      let top = 0;
      while (node && !(node.scrollHeight > node.clientHeight + 40 && /(auto|scroll)/.test(getComputedStyle(node).overflowY))) {
        top += node.offsetTop;
        node = node.offsetParent as HTMLElement | null;
      }
      return top;
    });
    await slowScroll(page, box, Math.max(0, offset - 40), 2600);
    await page.waitForTimeout(300);
    await rec.focus(dialog.getByText(/CONFRONTO CON GLI ALTRI FILE/i).first(), 1.6, 60);
    await page.waitForTimeout(300);
    await moveTo(page, dialog.getByText("Divergenze (3)").first(), 700);
    await page.waitForTimeout(500);
    await moveTo(page, dialog.getByText(/non so da chi/).first(), 900);
    await page.waitForTimeout(909);
    await moveTo(page, dialog.getByText(/la faccio io/).first(), 900);
    await page.waitForTimeout(1560);
  });
});

test("05-lacuna", async ({ page }) => {
  await scene(page, "05-lacuna", async () => {
    await page.goto(P);
    await expect(page.getByRole("button", { name: /^Decidi$/ })).toBeVisible();
  }, async (rec) => {
    await clickOn(page, page.getByRole("button", { name: /^Decidi$/ }));
    await page.waitForTimeout(900);
    await clickOn(page, page.getByRole("button", { name: /Da decidere/ }));
    await page.waitForTimeout(700);
    await rec.focus(page.getByText(/Qual e' la soglia di importo/).first(), 1.8, 160);
    await moveTo(page, page.getByText(/Qual e' la soglia di importo/).first(), 900);
    await page.waitForTimeout(979);
    await moveTo(page, page.getByText("Chiedo la procedura scritta a Francesca"), 800);
    await page.waitForTimeout(1560);
  });
});

test("06-as-is", async ({ page }) => {
  await scene(page, "06-as-is", async () => {
    await page.goto(`${P}?view=canvas`);
    await expect(page.locator("[data-element-id='percorso_urgente_regolarizza_ordine']").first()).toBeVisible();
  }, async (rec) => {
    await clickOn(page, page.getByRole("button", { name: "Evidenze" }));
    const panel = page.getByRole("complementary", { name: "Evidenze del disegno" });
    await expect(panel).toContainText("100%");
    await page.waitForTimeout(300);
    await rec.focus(panel, 1.5, 16);
    await page.waitForTimeout(600);
    await moveTo(page, panel.getByText("Il disegno coincide con le fonti"), 800);
    await page.waitForTimeout(900);
    await clickOn(page, panel.locator("summary", { hasText: "Citati dalle fonti" }));
    await page.waitForTimeout(700);
    const quote = panel.getByText(/ricostruire la pratica a posteriori/).first();
    await quote.scrollIntoViewIfNeeded();
    await moveTo(page, quote, 900);
    await page.waitForTimeout(800);
    rec.wide();
    await moveTo(page, page.locator("[data-element-id='percorso_urgente_regolarizza_ordine']").first(), 900);
    await rec.focus(page.locator("[data-element-id='percorso_urgente_regolarizza_ordine']").first(), 2, 200);
    await page.waitForTimeout(1440);
  });
});


test("08-as-is-corretto", async ({ page }) => {
  await scene(page, "08-as-is-corretto", async () => {
    await page.goto(`${P}?view=canvas`);
    await expect(page.locator(`[data-element-id='${AS_IS_REVIEW_NODE}']`).first()).toBeVisible();
  }, async (rec) => {
    await clickOn(page, page.locator(`[data-element-id='${AS_IS_REVIEW_NODE}']`).first());
    await clickOn(page, page.getByRole("button", { name: "Proprietà", exact: true }));
    await expect(page.getByRole("tablist", { name: "Schede proprietà" })).toBeVisible();
    await page.waitForTimeout(300);
    await rec.focus(page.getByLabel("Responsabile attività"), 1.8, 180);
    await moveTo(page, page.getByLabel("Responsabile attività"), 800);
    await page.waitForTimeout(1200);
    rec.wide();
    await clickOn(page, page.getByRole("button", { name: "Importa, esporta, cronologia" }));
    await page.waitForTimeout(400);
    await clickOn(page, page.getByRole("menuitem", { name: /Cronologia versioni/ }));
    await page.waitForTimeout(400);
    await rec.focus(page.getByText("As-Is v3 · validato con Laura Conti").first(), 1.9, 160);
    await page.waitForTimeout(200);
    await moveTo(page, page.getByText("As-Is v3 · validato con Laura Conti").first(), 900);
    await page.waitForTimeout(2000);
  });
});

async function replayScene(page: Page, id: string, run: number): Promise<void> {
  await scene(page, id, async () => {
    await page.goto(`${P}/simulation/replay/${run}`);
    await expect(page.getByRole("button", { name: "Riproduci", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Mostra tutta la tela" }).click();
    await page.getByRole("combobox", { name: "Velocità" }).click();
    await page.getByRole("option", { name: "≈ 40 s" }).click();
    await page.waitForTimeout(800);
  }, async (rec) => {
    await clickOn(page, page.getByRole("button", { name: "Riproduci", exact: true }), 600);
    await moveTo(page, { x: 960, y: 1040 }, 500);
    // Prima i token sul processo, poi i grafici che si muovono.
    await rec.focus({ x: 80, y: 160, width: 1340, height: 660 }, 1.3, 0);
    await page.waitForTimeout(4500);
    await rec.focus({ x: 80, y: 600, width: 1820, height: 420 }, 1.25, 0);
    await page.waitForTimeout(3400);
    rec.wide();
    await page.waitForTimeout(1600);
  });
}

test("09-simula-as-is", async ({ page }) => replayScene(page, "09-simula-as-is", IDS.asIsRun));
test("14-simula-to-be", async ({ page }) => replayScene(page, "14-simula-to-be", IDS.toBeRun));

test("10-heatmap", async ({ page }) => {
  await scene(page, "10-heatmap", async () => {
    await page.goto(`${P}/simulation/heatmap/${IDS.asIsRun}`);
    await expect(page.getByText("Collo di bottiglia").first()).toBeVisible();
    await page.getByRole("button", { name: "Mostra tutta la tela" }).click();
    await page.waitForTimeout(600);
  }, async (rec) => {
    await rec.focus(page.locator("[data-element-id='percorso_autorizzazione_autorizza_spesa']").first(), 2.2, 220);
    await moveTo(page, page.locator("[data-element-id='percorso_autorizzazione_autorizza_spesa']").first(), 1000);
    await page.waitForTimeout(1200);
    await rec.focus(page.getByText("Collo di bottiglia").first(), 1.8, 200);
    await moveTo(page, page.getByText("Collo di bottiglia").first(), 900);
    await page.waitForTimeout(1200);
    await moveTo(page, page.getByText("Quota dell'attesa totale").first(), 800);
    await page.waitForTimeout(2200);
  });
});

test("11-event-log", async ({ page }) => {
  await scene(page, "11-event-log", async () => {
    await page.goto(`${P}/simulation`);
    await expect(page.getByRole("button", { name: "Event log", exact: true })).toBeVisible();
  }, async (rec) => {
    await clickOn(page, page.getByRole("button", { name: "Event log", exact: true }));
    await page.waitForTimeout(700);
    await clickOn(page, page.getByRole("button", { name: /^export-workflow-acquisti\.csv/ }).first());
    await page.waitForTimeout(400);
    await rec.focus({ x: 1430, y: 160, width: 480, height: 820 }, 1.6, 0);
    await page.waitForTimeout(500);
    await clickOn(page, page.getByRole("button", { name: /Qualità e KPI/ }).first());
    await page.waitForTimeout(1600);
    await clickOn(page, page.getByRole("button", { name: /Reale contro simulato/ }).first());
    await page.waitForTimeout(800);
    // Il log e' di oggi: si confronta con la simulazione dell'As-Is.
    const run = page.getByRole("combobox", { name: "Run simulato" });
    await moveTo(page, run, 700);
    await run.selectOption({ value: String(IDS.asIsRun) }).catch(async () => run.selectOption({ index: 1 }));
    await expect(page.getByText(/vicino al reale/).first()).toBeVisible();
    await rec.focus(page.getByText(/vicino al reale/).first(), 2.0, 140);
    await page.waitForTimeout(500);
    await moveTo(page, page.getByText(/vicino al reale/).first(), 900);
    await page.waitForTimeout(2200);
  });
});


test("13-ipotesi-to-be", async ({ page }) => {
  await scene(page, "13-ipotesi-to-be", async () => {
    await page.goto(P);
    await expect(page.getByRole("tab", { name: "Ipotesi To-Be" })).toBeVisible();
  }, async (rec) => {
    await clickOn(page, page.getByRole("tab", { name: "Ipotesi To-Be" }));
    await expect(page.getByText("La richiesta nasce completa, con i campi obbligatori")).toBeVisible();
    await page.waitForTimeout(300);
    await rec.focus(page.getByText("La richiesta nasce completa, con i campi obbligatori"), 1.7, 220);
    await page.waitForTimeout(400);
    await moveTo(page, page.getByText(/Un posto unico dove la richiesta/).first(), 900);
    await page.waitForTimeout(1260);
    await rec.focus(page.getByText(/vorrei che l'autorizzazione/).first(), 1.7, 220);
    await moveTo(page, page.getByText(/vorrei che l'autorizzazione/).first(), 900);
    await page.waitForTimeout(1560);
  });
});

test("15-decidi", async ({ page }) => {
  await scene(page, "15-decidi", async () => {
    await page.goto(`${P}/simulation/compare?a=${IDS.asIsRun}&b=${IDS.toBeRun}`);
    await expect(page.getByText(/attraversamento −/)).toBeVisible();
    await page.getByRole("button", { name: "Mostra tutta la tela" }).click();
  }, async (rec) => {
    await rec.focus(page.getByText(/attraversamento −/), 1.9, 160);
    await moveTo(page, page.getByText(/attraversamento −/), 1000);
    await page.waitForTimeout(1260);
    rec.wide();
    await moveTo(page, page.locator("[data-element-id='percorso_autorizzazione_autorizza_spesa']").first(), 1000);
    await page.waitForTimeout(1800);
  });
});

/**
 * DeliR non ha (ancora) un invio al process owner: il consulente apre la
 * proposta To-Be, scarica il BPMN e il progetto segna il passo successivo.
 */
test("16-process-owner", async ({ page }) => {
  await scene(page, "16-process-owner", async () => {
    await page.goto(`${P}?view=review`);
    await expect(page.locator(`.review-canvas [data-element-id='${REVIEW_NODE}']`).first()).toBeVisible();
    await page.getByRole("button", { name: /^Task \d+$/ }).first().click();
    await page.getByRole("button", { name: "Autorizza spesa", exact: true }).click();
    await page.getByRole("button", { name: "Apri agente DeliR", exact: true }).click();
    const chat = page.getByRole("dialog", { name: "Agente di Review" });
    await page.getByLabel("Scrivi all’agente di Review").fill(reviewQuestion);
    await page.getByRole("button", { name: "Invia messaggio", exact: true }).click();
    await expect(chat.getByText(/Da verificare con Laura Conti/).first()).toBeVisible({ timeout: 30_000 });
    await chat.getByRole("button", { name: "Apri conoscenza e proposte del task" }).click();
    await page.getByRole("tab", { name: "Proposte", exact: true }).click();
    await page.waitForTimeout(500);
  }, async (rec) => {
    await clickOn(page, page.getByRole("button", { name: "Apri diagramma", exact: true }).first());
    const preview = page.getByRole("dialog").filter({ has: page.getByRole("button", { name: "Scarica BPMN" }) });
    await expect(preview).toBeVisible();
    await page.waitForTimeout(300);
    await rec.focus(preview, 1.5, 16);
    await page.waitForTimeout(1200);
    await clickOn(page, preview.getByRole("button", { name: "Scarica BPMN" }));
    await page.waitForTimeout(1300);
    rec.wide();
    await page.goto(`/projects/${IDS.project}`);
    await expect(page.getByText(`Validazione del To-Be con ${PROCESS_OWNER}`)).toBeVisible();
    await rec.focus(page.getByText(`Validazione del To-Be con ${PROCESS_OWNER}`), 2.2, 120);
    await moveTo(page, page.getByText(`Validazione del To-Be con ${PROCESS_OWNER}`), 900);
    await page.waitForTimeout(1800);
  });
});

test("17-memoria", async ({ page }) => {
  await scene(page, "17-memoria", async () => {
    await page.goto(`/projects/${IDS.project}`);
    await expect(page.getByRole("tab", { name: /Fonti/ })).toBeVisible();
  }, async (rec) => {
    const nav = (name: string) => page.getByRole("button", { name, exact: true }).first();
    await clickOn(page, nav("Clienti"));
    await page.waitForTimeout(840);
    await clickOn(page, page.getByText("Vetrano Industriale S.p.A.").first());
    await page.waitForTimeout(1260);
    await clickOn(page, nav("Home"));
    rec.wide();
    rec.mark("portfolio");
    await page.waitForTimeout(3400);
  });
});

// --- Screenshot per la landing (doppia densita') ----------------------------

test.describe("screens", () => {
  test.use({ deviceScaleFactor: 2 });

  test("landing screenshots", async ({ page }) => {
    const dir = resolve(OUT, "screens");
    mkdirSync(dir, { recursive: true });
    const shot = async (name: string) => {
      // Negli screenshot il cursore non serve.
      await page.evaluate(() => document.getElementById("launch-cursor")?.remove());
      await page.screenshot({ path: resolve(dir, `${name}.png`) });
    };

    await page.goto(`${P}?view=canvas`);
    await expect(page.locator("[data-element-id='percorso_urgente_regolarizza_ordine']").first()).toBeVisible();
    await page.getByRole("button", { name: "Evidenze" }).click();
    await expect(page.getByRole("complementary", { name: "Evidenze del disegno" })).toContainText("100%");
    await shot("01-hero-processo-validato");

    await page.goto(`${P}?view=canvas`);
    await page.locator("[data-element-id='percorso_autorizzazione_autorizza_spesa']").first().click();
    await page.getByRole("button", { name: "Proprietà", exact: true }).click();
    await page.getByRole("tablist", { name: "Schede proprietà" }).getByRole("tab", { name: "Regole" }).click();
    await expect(page.getByText(/Nessun sostituto formale/).first()).toBeVisible();
    await shot("01b-proprieta-del-task");

    await page.goto(P);
    await expect(page.getByText(/Ho letto le tre interviste/).first()).toBeVisible();
    await shot("01c-chat-con-delir");

    for (const [name, node, task, question, done] of [
      ["05b-review-as-is", AS_IS_REVIEW_NODE, "Regolarizza ordine a posteriori", asIsReviewQuestion, /Da confermare con Laura Conti/],
      ["05c-review-to-be", REVIEW_NODE, "Autorizza spesa", reviewQuestion, /Da verificare con Laura Conti/],
    ] as const) {
      await page.goto(`${P}?view=review`);
      await expect(page.locator(`.review-canvas [data-element-id='${node}']`).first()).toBeVisible();
      await page.getByRole("button", { name: /^Task \d+$/ }).first().click();
      await page.getByRole("button", { name: task, exact: true }).click();
      await page.getByRole("button", { name: "Apri agente DeliR", exact: true }).click();
      await page.getByLabel("Scrivi all’agente di Review").fill(question);
      await page.getByRole("button", { name: "Invia messaggio", exact: true }).click();
      await expect(page.getByRole("dialog", { name: "Agente di Review" }).getByText(done).first()).toBeVisible({ timeout: 30_000 });
      await page.waitForTimeout(600);
      await shot(name);
    }

    await page.goto(`${P}/simulation`);
    await page.getByRole("button", { name: "Event log", exact: true }).click();
    await page.getByRole("button", { name: /^export-workflow-acquisti\.csv/ }).first().click();
    await page.getByRole("button", { name: /Reale contro simulato/ }).first().click();
    await page.getByRole("combobox", { name: "Run simulato" }).selectOption({ value: String(IDS.asIsRun) });
    await expect(page.getByText(/vicino al reale/).first()).toBeVisible();
    await page.waitForTimeout(600);
    await shot("07c-event-log-reale-contro-simulato");

    await openSources(page);
    await page.getByRole("tab", { name: /Fonti/ }).click();
    await page.getByText("Intervista Laura Conti").first().click();
    await page.waitForTimeout(800);
    await shot("02-fonti-e-affermazioni");
    await page.keyboard.press("Escape");
    await page.getByText("Intervista Francesca Neri").first().click();
    await page.getByRole("dialog").getByText("Divergenze (3)").first().scrollIntoViewIfNeeded();
    await page.waitForTimeout(800);
    await shot("03-passaggio-nascosto");

    await page.goto(P);
    await page.getByRole("button", { name: /^Decidi$/ }).click();
    await page.getByRole("button", { name: /Da decidere/ }).click();
    await page.waitForTimeout(600);
    await shot("04-lacuna-aperta");
    await page.keyboard.press("Escape");

    await page.goto(P);
    await page.getByRole("tab", { name: "Ipotesi To-Be" }).click();
    await expect(page.getByText("La richiesta nasce completa, con i campi obbligatori")).toBeVisible();
    await shot("05-ipotesi-to-be");

    for (const [name, run] of [["06-simulazione-as-is", IDS.asIsRun], ["07-simulazione-to-be", IDS.toBeRun]] as const) {
      await page.goto(`${P}/simulation/replay/${run}`);
      await page.getByRole("button", { name: "Mostra tutta la tela" }).click();
      await page.getByRole("combobox", { name: "Velocità" }).click();
      await page.getByRole("option", { name: "≈ 40 s" }).click();
      await page.getByRole("button", { name: "Riproduci", exact: true }).click();
      await page.waitForTimeout(11_000);
      await page.getByRole("button", { name: "Pausa", exact: true }).click();
      await page.waitForTimeout(400);
      await shot(name);
    }

    await page.goto(`${P}/simulation/heatmap/${IDS.asIsRun}`);
    await expect(page.getByText("Collo di bottiglia").first()).toBeVisible();
    await page.getByRole("button", { name: "Mostra tutta la tela" }).click();
    await page.waitForTimeout(800);
    await shot("07b-heatmap-collo-di-bottiglia");

    await page.goto(`${P}/simulation/compare?a=${IDS.asIsRun}&b=${IDS.toBeRun}`);
    await expect(page.getByText(/attraversamento −/)).toBeVisible();
    await page.getByRole("button", { name: "Mostra tutta la tela" }).click();
    await page.waitForTimeout(800);
    await shot("08-confronto-as-is-to-be");

    await page.goto(`/projects/${IDS.project}`);
    await expect(page.getByText(`Validazione del To-Be con ${PROCESS_OWNER}`)).toBeVisible();
    await shot("09-memoria-del-progetto");

    await page.goto("/home");
    await expect(page.getByText("Vetrano Industriale S.p.A.").first()).toBeVisible();
    await shot("10-portafoglio-clienti");
  });
});

// --- Testi a schermo come PNG trasparenti (li sovrappone il montaggio) ------

test("overlays", async ({ page }) => {
  const dir = resolve(OUT, "overlays");
  mkdirSync(dir, { recursive: true });
  await page.goto("/home");
  await expect(page.getByText("Acquisti indiretti e servizi").first()).toBeVisible();
  const font = (await page.evaluate(() => getComputedStyle(document.body).fontFamily)).replace(/"/g, "'");
  const esc = (text: string) => text.replace(/&/g, "&amp;").replace(/</g, "&lt;");
  const render = async (name: string, body: string) => {
    await page.setContent(`<!doctype html><html><body style="margin:0;background:transparent;font-family:${font}">${body}</body></html>`);
    await page.screenshot({ path: resolve(dir, `${name}.png`), omitBackground: true });
  };

  // Testi delle scene: il montaggio li fa entrare dal basso.
  const texts: Record<string, string> = {};
  for (const item of storyboard.scenes) {
    if (item.caption) texts[item.id] = item.caption;
    (item.captions ?? []).forEach((extra, index) => { texts[`${item.id}-${index + 1}`] = extra.text; });
  }
  for (const [name, text] of Object.entries(texts)) {
    await render(name, `<div style="position:fixed;inset:0;display:flex;align-items:flex-end;justify-content:center;padding:0 0 110px 0">
      <div style="font-size:50px;font-weight:600;letter-spacing:-0.02em;color:#fff;background:rgba(15,23,42,.9);border-radius:22px;padding:24px 44px;box-shadow:0 24px 70px rgba(15,23,42,.35);max-width:1500px;text-align:center">${esc(text)}</div></div>`);
  }

  await render("disclaimer", `<div style="position:fixed;right:18px;bottom:12px;font-size:14px;color:#64748b;background:rgba(255,255,255,.9);border:1px solid #e2e8f0;border-radius:999px;padding:5px 12px">${esc(storyboard.disclaimer)}</div>`);

  // Il percorso del consulente: una tappa accesa per volta, le precedenti fatte.
  for (let current = 0; current <= storyboard.stages.length; current += 1) {
    const steps = storyboard.stages.map((label, index) => {
      const done = index < current;
      const now = index === current;
      const dot = done
        ? `<span style="display:inline-grid;place-items:center;width:20px;height:20px;border-radius:50%;background:#16a34a;color:#fff;font-size:12px">✓</span>`
        : `<span style="display:inline-grid;place-items:center;width:20px;height:20px;border-radius:50%;background:${now ? "#2563eb" : "#e2e8f0"};color:${now ? "#fff" : "#64748b"};font-size:12px;font-weight:600">${index + 1}</span>`;
      return `<span style="display:inline-flex;align-items:center;gap:7px;padding:5px 10px;border-radius:999px;${now ? "background:#eff6ff;" : ""}color:${now ? "#1d4ed8" : done ? "#0f172a" : "#94a3b8"};font-weight:${now ? 650 : 500}">${dot}${esc(label)}</span>`;
    });
    await render(`stage-${current}`, `<div style="position:fixed;top:7px;left:0;right:0;display:flex;justify-content:center">
      <div style="display:flex;align-items:center;gap:2px;font-size:14px;background:rgba(255,255,255,.96);border:1px solid #e2e8f0;border-radius:999px;padding:3px 5px;box-shadow:0 8px 26px rgba(15,23,42,.12)">${steps.join('<span style="color:#cbd5e1">›</span>')}</div></div>`);
  }
});
