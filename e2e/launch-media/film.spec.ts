/**
 * Le riprese dei moduli del prodotto (filmPlan.ts): le clip delle 5 tab di
 * delir.it e il film che le mette in fila, sul caso Vetrano, in italiano e in
 * inglese, da desktop 1440x900 a densita' 2.
 *
 * Stesse regole dell'hero: tempo virtuale a 30 fps esatti, velocita' 1x,
 * cursore da 1,2 s, scrittura a 70 ms per carattere, DeliR in streaming alla
 * velocita' del prodotto (filmChat.ts). Ogni scena parte dal desktop intero e
 * zooma quando succede qualcosa (decisione del 14 ottobre). Sul sito la clip
 * e' larga 724 px: gli zoom stanno entro circa 700-900 px di pagina, perche'
 * il testo resti leggibile.
 * Le scene che i moduli riprendono dall'hero non si girano qui.
 *
 *   npx playwright test -c playwright.launch.config.ts film --project=desktop
 *   python3 scripts/launch_media_montage.py film
 */
import { expect, test, type Locator, type Page } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";

import { installCaseApi } from "./caseApi";
import { PROMPTS, installChatStream, type ChatKind } from "./filmChat";
import { FILM_INTRO, FILM_OUTRO, MODULES } from "./filmPlan";
import { OVERLAYS, box, calm, record, union, type Rect } from "./kit";
import { unhandled } from "./mockApi";
import { clickOn, installCursor, moveTo, pause, typeHuman, type VirtualRecorder } from "./recorder";
import { IDS, type Lang } from "./vetrano";

test.use({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
test.skip(Boolean(process.env.CI) && process.env.DELIR_LAUNCH_MEDIA !== "1", "Generatore di media: in CI con DELIR_LAUNCH_MEDIA=1");

const P = `/projects/${IDS.project}/processes/${IDS.process}`;

const UI = {
  it: {
    evidence: /Revisione delle evidenze del disegno/,
    awaiting: "Da confermare",
    openAgent: "Apri agente DeliR",
    send: /Invia al cliente/,
    sent: "Ho inviato il link",
    approve: "Il cliente ha approvato",
    consultantDone: "versioni non tornano",
    processDone: "te la chiedo",
    reviewDone: "assunzioni dello scenario",
    open: "Da chiarire prima del workshop",
    search: "acqu",
  },
  en: {
    evidence: /Review the drawing against the evidence/,
    awaiting: "To confirm",
    openAgent: "Open DeliR agent",
    send: /Send to client/,
    sent: "I sent the link",
    approve: "Client approved",
    consultantDone: "accounts don't match",
    processDone: "I'm asking you",
    reviewDone: "scenario assumptions",
    open: "To clarify before the workshop",
    search: "purch",
  },
} as const;

test.afterAll(() => {
  if (unhandled.size) console.warn("Richieste non coperte dal caso demo:", [...unhandled].join(", "));
});

/** Il link del cliente nel dialog: delir.it gia' quando il campo riceve il valore. */
async function showPublicLink(page: Page): Promise<void> {
  await page.evaluate((origin) => {
    const swap = (value: string) => value.replace(origin, "https://delir.it");
    const property = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!;
    Object.defineProperty(HTMLInputElement.prototype, "value", { ...property, set(this: HTMLInputElement, value: string) { property.set!.call(this, swap(value)); } });
  }, new URL(page.url()).origin);
}

/** Il desktop intero, prima di ogni azione: si vede sempre il prodotto (decisione del 14 ottobre). */
async function establish(page: Page, rec: VirtualRecorder, ms = 1400): Promise<void> {
  const view = page.viewportSize()!;
  await rec.focus({ x: 0, y: 0, width: view.width, height: view.height }, 1, 0, { overview: true });
  await rec.wait(ms);
}

/**
 * Scrive a DeliR come una persona e segue la risposta: il desktop, poi il box
 * di scrittura, la domanda con le fasi di lavoro, e la risposta mentre arriva.
 */
async function converse(page: Page, rec: VirtualRecorder, lang: Lang, kind: ChatKind, done: string, composer: Locator): Promise<void> {
  await establish(page, rec);
  const input = await box(composer);
  await rec.focus(input, 4, 12);
  await typeHuman(page, composer, PROMPTS[lang][kind]);
  await pause(page, 300);
  await page.keyboard.press("Enter");
  const asked = page.getByText(PROMPTS[lang][kind], { exact: true }).last();
  await rec.waitUntil(() => asked.isVisible());
  await moveTo(page, { x: -10, y: -10 }, 10);
  // La domanda e le fasi di lavoro di DeliR.
  const question = await box(asked);
  await rec.focus({ x: input.x - 8, y: question.y - 12, width: 700, height: 220 }, 4, 0);
  // La risposta, dalla prima riga in giu', mentre arriva: il blocco del testo,
  // sotto le fasi di lavoro.
  const first = page.locator(".message.assistant").last().locator("p").first();
  await rec.waitUntil(() => first.isVisible(), 20_000);
  const start = await box(first.locator("xpath=.."));
  // Fino al box di scrittura, o alla fascia della decisione sopra di lui.
  const decision = page.getByText(lang === "it" ? "Serve una tua decisione" : "Your decision is needed").first();
  const bottom = Math.min((await box(composer)).y, (await decision.isVisible()) ? (await box(decision)).y - 10 : Infinity) - 8;
  // Margine sopra per la targhetta; una risposta breve non porta con se' il vuoto sotto.
  const height = Math.min(Math.max(160, bottom - start.y + 44), kind === "consultant" ? 230 : 460);
  await rec.focus({ x: input.x - 24, y: start.y - 44, width: input.width + 32, height }, 4, 0);
  await rec.waitUntil(() => page.getByText(done, { exact: false }).last().isVisible(), 40_000);
}

const SCENES: Record<string, (page: Page, lang: Lang, id: string) => Promise<void>> = {
  // --- Contesto

  "01-home": async (page, lang, id) => {
    await page.goto("/home");
    const first = page.getByText(lang === "it" ? "Acquisti indiretti" : "Indirect purchasing").first();
    await expect(page.getByText("Brenta Alimentare S.p.A.").first()).toBeVisible();
    await page.waitForTimeout(600);
    await calm(page);
    // I progetti, con il cliente di ciascuno: la lista dei clienti sta nella card accanto.
    const projects = union(await box(first), await box(page.getByText(/Brenta Alimentare S\.p\.A\. ·/).first()));
    await record(page, id, async (rec) => {
      await establish(page, rec);
      await rec.focus(projects, 4, 40);
      await rec.wait(1200);
      await moveTo(page, first);
      await rec.wait(2000);
    });
  },

  "02-consulente": async (page, lang, id) => {
    await page.goto("/consultant");
    const composer = page.getByRole("textbox").last();
    await expect(composer).toBeVisible();
    await page.waitForTimeout(800);
    await calm(page);
    await record(page, id, async (rec) => {
      await converse(page, rec, lang, "consultant", UI[lang].consultantDone, composer);
      await rec.wait(3000);
    });
  },

  "18-ritrova": async (page, lang, id) => {
    await page.goto("/models");
    await expect(page.getByRole("table").first()).toBeVisible();
    await page.waitForTimeout(800);
    await calm(page);
    await record(page, id, async (rec) => {
      await establish(page, rec);
      await page.keyboard.press("Control+k");
      const dialog = page.getByRole("dialog");
      await rec.waitUntil(() => dialog.isVisible());
      const top = await box(dialog);
      await rec.focus({ ...top, height: Math.min(top.height, 200) }, 4, 8);
      await typeHuman(page, dialog.locator("input").first(), UI[lang].search);
      await moveTo(page, { x: -10, y: -10 }, 10);
      await rec.wait(600);
      // I primi risultati: progetto, processo, fonti.
      const found = await box(dialog);
      await rec.focus({ ...found, height: Math.min(found.height, 320) }, 4, 8);
      await rec.wait(3000);
    });
  },

  // --- Lacune

  "05-discussione": async (page, lang, id) => {
    await page.goto(`${P}?view=chat`);
    const composer = page.getByRole("textbox").last();
    await expect(composer).toBeVisible();
    await page.waitForTimeout(800);
    await calm(page);
    await record(page, id, async (rec) => {
      await converse(page, rec, lang, "process", UI[lang].processDone, composer);
      await rec.wait(600);
      // Le domande aperte: la divergenza e la lacuna.
      const open = await box(page.getByText(UI[lang].open).last());
      const end = await box(page.getByText(UI[lang].processDone, { exact: false }).last());
      const input = await box(composer);
      await rec.focus({ x: input.x - 24, y: open.y - 10, width: input.width + 32, height: end.y + end.height - open.y + 20 }, 4, 0);
      await rec.wait(4000);
    });
  },

  "08-da-confermare": async (page, lang, id) => {
    await page.goto(`${P}?view=canvas`);
    const evidence = page.getByRole("button", { name: UI[lang].evidence });
    await expect(evidence).toBeVisible();
    await page.waitForTimeout(800);
    await calm(page);
    const panel = page.locator(".process-evidence-panel");
    // Il verdetto del confronto, poi i tre elementi senza fonte con Conferma e Rifiuta.
    const verdict = panel.getByText(lang === "it" ? /coincide con le fonti/ : /matches the sources/i).first();
    const read = panel.getByText(lang === "it" ? "Fonti lette" : "Sources read").first();
    const awaiting = panel.getByText(UI[lang].awaiting, { exact: false }).nth(1);
    await record(page, id, async (rec) => {
      await establish(page, rec, 900);
      await clickOn(page, evidence);
      await rec.waitUntil(() => panel.isVisible());
      await rec.wait(500);
      await moveTo(page, { x: -10, y: -10 }, 10);
      await rec.focus(union(await box(verdict), await box(read)), 4, 16);
      await rec.wait(2200);
      const list = await box(awaiting);
      await rec.focus({ x: list.x - 8, y: list.y - 8, width: (await box(panel)).width - 16, height: 260 }, 4, 4);
      await moveTo(page, panel.getByText(lang === "it" ? "Integra la richiesta" : /Supplement the request|Complete the request/).first());
      await rec.wait(2600);
    });
  },

  // --- Scenari

  "09-review": async (page, lang, id) => {
    await page.goto(`${P}?view=review`);
    const task = page.locator("[data-element-id='Task_Valuta']").first();
    await expect(task).toBeVisible();
    // Il pannello di DeliR allargato, come lo allarga il consulente: la risposta si legge.
    await page.addStyleTag({ content: ".review-agent-chat { width: 560px !important; height: 520px !important; }" });
    await page.waitForTimeout(800);
    await calm(page);
    const composer = page.getByRole("textbox").last();
    const transcript = page.locator(".review-chat-transcript");
    const input = page.locator(".review-chat-input");
    await record(page, id, async (rec) => {
      await establish(page, rec, 900);
      await clickOn(page, task);
      await clickOn(page, page.getByRole("button", { name: UI[lang].openAgent }));
      await rec.waitUntil(() => input.isVisible());
      await rec.focus(await box(input), 4, 12);
      await typeHuman(page, composer, PROMPTS[lang].review);
      await pause(page, 300);
      await page.keyboard.press("Enter");
      await moveTo(page, { x: -10, y: -10 }, 10);
      // La conversazione: domanda e risposta di DeliR, con le citazioni.
      await rec.focus(await box(transcript), 4, 4);
      await rec.waitUntil(() => page.getByText(UI[lang].reviewDone, { exact: false }).last().isVisible(), 40_000);
      await rec.wait(3500);
    });
  },

  // --- Decisioni

  "12-ipotesi": async (page, lang, id) => {
    await page.goto(`${P}?view=tobe`);
    const first = page.getByText(lang === "it" ? /nasce completa/ : /complete/i).first();
    await expect(first).toBeVisible();
    await page.waitForTimeout(800);
    await calm(page);
    const second = page.getByText(lang === "it" ? /Una delega/ : /deputy|delegat/i).first();
    await record(page, id, async (rec) => {
      await establish(page, rec);
      // Titolo e citazione di ogni proposta: la parte sinistra delle card.
      const a = await box(first);
      await rec.focus({ x: a.x - 24, y: a.y - 30, width: 700, height: 120 }, 4, 0);
      await moveTo(page, first);
      await rec.wait(2400);
      const b = await box(second);
      await rec.focus({ x: b.x - 24, y: b.y - 30, width: 700, height: 120 }, 4, 0);
      await moveTo(page, second);
      await rec.wait(2400);
    });
  },

  "16-cruscotto": async (page, lang, id) => {
    // Il processo e' gia' stato inviato: il cruscotto e' quello che legge il cliente.
    await page.goto(`${P}/handover`);
    await showPublicLink(page);
    await page.getByRole("button", { name: UI[lang].send }).click();
    await page.getByRole("button", { name: UI[lang].sent }).click();
    await expect(page.getByRole("button", { name: UI[lang].approve })).toBeVisible();
    await page.goto(`${P}/handover/dashboard`);
    const heading = page.getByRole("heading").first();
    await expect(heading).toBeVisible();
    await page.waitForTimeout(800);
    await calm(page);
    await record(page, id, async (rec) => {
      await establish(page, rec);
      // Una finestra di lettura sulla colonna del cruscotto; la pagina scorre sotto.
      const column = await box(heading);
      await rec.focus({ x: column.x - 24, y: column.y - 40, width: 700, height: 390 }, 4, 0);
      await rec.wait(1800);
      for (let step = 0; step < 40; step++) {
        await page.mouse.wheel(0, 14);
        await pause(page, 60);
      }
      await rec.wait(2500);
    });
  },

  "17-approvato": async (page, lang, id) => {
    await page.goto(`${P}/handover`);
    await showPublicLink(page);
    await page.getByRole("button", { name: UI[lang].send }).click();
    await page.getByRole("button", { name: UI[lang].sent }).click();
    const approve = page.getByRole("button", { name: UI[lang].approve });
    await expect(approve).toBeVisible();
    await page.waitForTimeout(800);
    await calm(page);
    const banner = page.locator(".handover-status").first();
    await record(page, id, async (rec) => {
      await establish(page, rec);
      // La parte destra dell'intestazione, con i due esiti della risposta del cliente.
      const top = await box(banner);
      const button = await box(approve);
      await rec.focus({ x: button.x + button.width - 640, y: top.y, width: 660, height: top.height }, 4, 8);
      await rec.wait(1000);
      await clickOn(page, approve);
      const dialog = page.getByRole("alertdialog").or(page.getByRole("dialog")).first();
      await rec.waitUntil(() => dialog.isVisible());
      await rec.focus(await box(dialog), 4, 16);
      await rec.wait(1500);
      // L'esito: approvato dal cliente, la parte sinistra dell'intestazione. La
      // camera parte insieme al clic, mentre il dialog si chiude.
      const done = await box(banner);
      await rec.focus({ x: done.x, y: done.y, width: 660, height: done.height }, 4, 8);
      await clickOn(page, dialog.getByRole("button", { name: UI[lang].approve }), 600);
      await rec.waitUntil(async () => !(await dialog.isVisible()));
      await moveTo(page, { x: -10, y: -10 }, 10);
      await rec.wait(3000);
    });
  },
};

for (const lang of ["it", "en"] as const) {
  test.describe(`film ${lang}`, () => {
    test.beforeEach(async ({ page }) => {
      page.setDefaultTimeout(20_000);
      await page.clock.install();
      await installCaseApi(page, lang, { layout: "grid" });
      await installChatStream(page, lang);
      await installCursor(page);
    });
    for (const [name, scene] of Object.entries(SCENES)) {
      const id = `film-${lang}-${name}`;
      test(id, async ({ page }) => scene(page, lang, id));
    }
  });
}

// --- Le scritte, a 1920x1080: le targhette dei moduli e i cartelli del film.

const FONT = "system-ui,sans-serif";

/** La targhetta blu: il numero del passo e la frase. Nel film sopra c'e' il nome del modulo. */
const tagHtml = (number: number, text: string, module = "", size = 36) => `<div style="position:fixed;left:${size}px;top:${size}px">
  ${module ? `<div style="display:inline-block;margin:0 0 ${size * 0.3}px ${size * 0.2}px;padding:${size * 0.12}px ${size * 0.45}px;border-radius:999px;background:rgba(255,255,255,.94);color:#004580;
    font:700 ${size * 0.62}px/1.2 ${FONT};letter-spacing:.06em;text-transform:uppercase;box-shadow:0 2px 8px rgba(0,30,70,.18)">${module}</div><br>` : ""}
  <div style="display:inline-flex;align-items:center;gap:${size * 0.4}px;padding:${size * 0.38}px ${size * 0.75}px ${size * 0.38}px ${size * 0.38}px;border-radius:999px;
    background:#004580;color:#fff;box-shadow:0 ${size * 0.3}px ${size}px -${size * 0.4}px rgba(0,30,70,.55);font:600 ${size}px/1.2 ${FONT}">
    <span style="display:grid;place-items:center;width:${size * 1.35}px;height:${size * 1.35}px;border-radius:999px;background:#fff;color:#004580;font-weight:700">${number}</span>
    <span>${text}</span></div></div>`;

const cardHtml = (title: string, line: string) => `<div style="position:fixed;inset:0;background:#0B1021;color:#fff;display:flex;flex-direction:column;justify-content:center;padding:0 160px">
  <div style="font:700 84px/1.08 ${FONT};max-width:1500px">${title}</div>
  <div style="font:400 40px/1.35 ${FONT};color:#C9D6E6;margin-top:36px;max-width:1400px">${line}</div>
  <div style="position:absolute;left:160px;bottom:90px;font:700 44px/1 ${FONT}">DeliR<span style="color:#0071E3">.</span></div></div>`;

test("film-overlays", async ({ page }) => {
  mkdirSync(OVERLAYS, { recursive: true });
  await page.setViewportSize({ width: 1920, height: 1080 });
  const shoot = async (html: string, name: string, transparent: boolean) => {
    await page.setContent(`<!doctype html><html><body style="margin:0;background:transparent">${html}</body></html>`);
    await page.screenshot({ path: resolve(OVERLAYS, `${name}-16x9.png`), omitBackground: transparent });
  };
  for (const lang of ["it", "en"] as const) {
    await shoot(cardHtml(FILM_INTRO[lang].title, FILM_INTRO[lang].line), `fcard-${lang}-intro`, false);
    await shoot(cardHtml(FILM_OUTRO[lang].title, FILM_OUTRO[lang].line), `fcard-${lang}-outro`, false);
    for (const module of MODULES) {
      let number = 0;
      for (const shot of module.shots) {
        for (const item of shot.tags) {
          number += 1;
          // Sul sito il nome della tab e' gia' intorno al video; nel film la targhetta lo dice.
          await shoot(tagHtml(number, item.text[lang]), `mtag-${lang}-${module.id}-${number}`, true);
          await shoot(tagHtml(number, item.text[lang], module.name[lang]), `ftag-${lang}-${module.id}-${number}`, true);
        }
      }
    }
  }
});
