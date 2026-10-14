/**
 * Le riprese del film del prodotto (filmPlan.ts): l'incarico intero sul caso
 * Vetrano, in italiano e in inglese, da desktop 1440x900 a densita' 2.
 *
 * Stesse regole dell'hero: tempo virtuale a 30 fps esatti, velocita' 1x,
 * cursore da 1,2 s, scrittura a 70 ms per carattere, DeliR in streaming alla
 * velocita' del prodotto (filmChat.ts), uno zoom per momento sull'area che
 * conta. Le scene che il film riprende dall'hero non si girano qui.
 *
 *   npx playwright test -c playwright.launch.config.ts film --project=desktop
 *   python3 scripts/launch_media_montage.py film
 */
import { expect, test, type Locator, type Page } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";

import { installCaseApi } from "./caseApi";
import { PROMPTS, installChatStream } from "./filmChat";
import { FILM, FILM_INTRO, FILM_OUTRO } from "./filmPlan";
import { OVERLAYS, box, calm, record, union, type Rect } from "./kit";
import { unhandled } from "./mockApi";
import { clickOn, installCursor, moveTo, pause, typeHuman } from "./recorder";
import { IDS, type Lang } from "./vetrano";

test.use({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
test.skip(Boolean(process.env.CI) && process.env.DELIR_LAUNCH_MEDIA !== "1", "Generatore di media: in CI con DELIR_LAUNCH_MEDIA=1");

const P = `/projects/${IDS.project}/processes/${IDS.process}`;

const UI = {
  it: {
    sources: "Fonti",
    interview: /Intervista Laura Conti/,
    divergenceClaim: "Non sa chi regolarizza un acquisto urgente",
    otherFiles: /Confronto con gli altri file/i,
    evidence: /Revisione delle evidenze del disegno/,
    awaiting: "Da confermare",
    openAgent: "Apri agente DeliR",
    whatToTry: "Cosa provare",
    createScenario: /Crea scenario/,
    ready: "Pronto per la consegna?",
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
    sources: "Sources",
    interview: /Interview Laura Conti/,
    divergenceClaim: "Doesn't know who regularizes an urgent purchase",
    otherFiles: /Comparison with other files|Cross-check/i,
    evidence: /Review the drawing against the evidence/,
    awaiting: "To confirm",
    openAgent: "Open DeliR agent",
    whatToTry: "What to try",
    createScenario: /Create scenario/,
    ready: "Ready to hand over?",
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

/** La colonna della conversazione, dal messaggio del consulente al box di scrittura. */
async function thread(page: Page, prompt: string, composer: Locator, rows = 0): Promise<Rect> {
  const input = await box(composer);
  const asked = await box(page.getByText(prompt, { exact: true }).last());
  const top = rows ? input.y - rows : asked.y - 12;
  return { x: input.x - 8, y: top, width: input.width + 16, height: input.y - top };
}

/** Scrive al consulente come una persona e aspetta che DeliR finisca di rispondere. */
async function converse(page: Page, rec: import("./recorder").VirtualRecorder, prompt: string, done: string, composer: Locator, rows = 0): Promise<void> {
  await rec.focus(await box(composer), 4, 24);
  await typeHuman(page, composer, prompt);
  await pause(page, 300);
  await page.keyboard.press("Enter");
  await rec.waitUntil(() => page.getByText(prompt, { exact: true }).last().isVisible());
  await moveTo(page, { x: -10, y: -10 }, 10);
  await rec.focus(await thread(page, prompt, composer, rows), 4, 8);
  await rec.waitUntil(() => page.getByText(done, { exact: false }).last().isVisible());
}

const SCENES: Record<string, (page: Page, lang: Lang, id: string) => Promise<void>> = {
  // --- Lo studio

  "01-home": async (page, lang, id) => {
    await page.goto("/home");
    await expect(page.getByText("Brenta Alimentare S.p.A.").first()).toBeVisible();
    await page.waitForTimeout(600);
    await calm(page);
    const main = await box(page.locator("main").first());
    const lists = union(await box(page.getByText(lang === "it" ? "Acquisti indiretti" : "Indirect purchasing").first()),
      await box(page.getByText("Brenta Alimentare S.p.A.").last()));
    await record(page, id, async (rec) => {
      await rec.focus(main, 4, 0, { overview: true });
      await rec.wait(1500);
      await rec.focus(lists, 4, 40);
      await rec.wait(1200);
      await moveTo(page, page.getByText(lang === "it" ? "Acquisti indiretti" : "Indirect purchasing").first());
      await rec.wait(1600);
    });
  },

  "02-consulente": async (page, lang, id) => {
    await page.goto("/consultant");
    const composer = page.getByRole("textbox").last();
    await expect(composer).toBeVisible();
    await page.waitForTimeout(800);
    await calm(page);
    await record(page, id, async (rec) => {
      await converse(page, rec, PROMPTS[lang].consultant, UI[lang].consultantDone, composer);
      await rec.wait(3000);
    });
  },

  "03-progetto": async (page, lang, id) => {
    await page.goto(`/projects/${IDS.project}`);
    const objective = page.getByText(lang === "it" ? /Ricostruire come nasce/ : /Rebuild how/).first();
    await expect(objective).toBeVisible();
    await page.waitForTimeout(600);
    await calm(page);
    const main = await box(page.locator("main").first());
    const milestones = page.getByRole("listitem").filter({ hasText: /Validazione|validation/i }).first();
    const focus = union(await box(objective), await box(milestones.or(objective).first()));
    await record(page, id, async (rec) => {
      await rec.focus(main, 4, 0, { overview: true });
      await rec.wait(1500);
      await rec.focus(focus, 4, 24);
      await rec.wait(3500);
    });
  },

  // --- Le fonti

  "04-fonti": async (page, lang, id) => {
    await page.goto(`/projects/${IDS.project}`);
    const tab = page.getByRole("tab", { name: UI[lang].sources }).or(page.getByRole("button", { name: UI[lang].sources, exact: true })).first();
    await expect(tab).toBeVisible();
    await page.waitForTimeout(600);
    await calm(page);
    await record(page, id, async (rec) => {
      await rec.focus(await box(page.locator("main").first()), 4, 0, { overview: true });
      await clickOn(page, tab);
      const interview = page.getByText(UI[lang].interview).first();
      await rec.waitUntil(() => interview.isVisible());
      const list = page.getByText(/Francesca Neri/).first();
      await rec.focus(union(await box(interview), await box(list)), 4, 40);
      await rec.wait(800);
      await clickOn(page, interview);
      const dialog = page.getByRole("dialog");
      await rec.waitUntil(() => dialog.isVisible());
      await rec.wait(500);
      await moveTo(page, { x: -10, y: -10 }, 10);
      // Le affermazioni, ognuna con la sua citazione verificata.
      const claim = dialog.getByText(UI[lang].divergenceClaim).first();
      await claim.scrollIntoViewIfNeeded();
      await rec.wait(200);
      const area = await box(dialog);
      const claimBox = await box(claim);
      await rec.focus({ x: area.x, y: Math.max(area.y, claimBox.y - 220), width: area.width, height: 300 }, 4, 8);
      await rec.wait(4000);
    });
  },

  "05-discussione": async (page, lang, id) => {
    await page.goto(`${P}?view=chat`);
    const composer = page.getByRole("textbox").last();
    await expect(composer).toBeVisible();
    await page.waitForTimeout(800);
    await calm(page);
    await record(page, id, async (rec) => {
      // La finestra segue la coda della risposta mentre arriva.
      await converse(page, rec, PROMPTS[lang].process, UI[lang].processDone, composer, 380);
      await rec.wait(800);
      // Le domande aperte: la divergenza e la lacuna.
      const open = page.getByText(UI[lang].open).last();
      const end = page.getByText(UI[lang].processDone, { exact: false }).last();
      await rec.focus(union(await box(open), await box(end)), 4, 16);
      await rec.wait(4000);
    });
  },

  // --- L'As-Is

  "08-da-confermare": async (page, lang, id) => {
    await page.goto(`${P}?view=canvas`);
    const evidence = page.getByRole("button", { name: UI[lang].evidence });
    await expect(evidence).toBeVisible();
    await page.waitForTimeout(800);
    await calm(page);
    await record(page, id, async (rec) => {
      await rec.focus(await box(page.locator(".process-bpmn-canvas").first()), 4, 0, { overview: true });
      await clickOn(page, evidence);
      const panel = page.locator(".process-evidence-panel");
      await rec.waitUntil(() => panel.isVisible());
      await rec.wait(400);
      await moveTo(page, { x: -10, y: -10 }, 10);
      // Il riepilogo e i tre elementi senza fonte, con Conferma e Rifiuta.
      const awaiting = panel.getByText(UI[lang].awaiting, { exact: true }).first();
      const top = await box(panel);
      const list = await box(awaiting);
      await rec.focus({ x: top.x, y: top.y + 40, width: top.width, height: list.y - top.y + 300 }, 4, 4);
      await rec.wait(4500);
    });
  },

  // --- La review

  "09-review": async (page, lang, id) => {
    await page.goto(`${P}?view=review`);
    const task = page.locator("[data-element-id='Task_Valuta']").first();
    await expect(task).toBeVisible();
    await page.waitForTimeout(800);
    await calm(page);
    await record(page, id, async (rec) => {
      await rec.focus(await box(page.locator(".process-bpmn-canvas, .process-review-workspace").first()), 4, 0, { overview: true });
      await clickOn(page, task);
      await clickOn(page, page.getByRole("button", { name: UI[lang].openAgent }));
      const composer = page.getByRole("textbox").last();
      await rec.waitUntil(() => composer.isVisible());
      const panel = union(await box(page.getByText(/DeliR \/ Review/).first()), await box(composer));
      await rec.focus(panel, 4, 8);
      await typeHuman(page, composer, PROMPTS[lang].review);
      await pause(page, 300);
      await page.keyboard.press("Enter");
      await moveTo(page, { x: -10, y: -10 }, 10);
      await rec.waitUntil(() => page.getByText(UI[lang].reviewDone, { exact: false }).last().isVisible());
      await rec.wait(3500);
    });
  },

  // --- La simulazione

  "11-insight": async (page, lang, id) => {
    await page.goto(`${P}/simulation/insights/${IDS.asIsRun}`);
    const title = page.getByText(UI[lang].whatToTry, { exact: true }).first();
    await expect(title).toBeVisible();
    await page.waitForTimeout(1200);
    await calm(page);
    const create = page.getByRole("button", { name: UI[lang].createScenario }).first();
    await record(page, id, async (rec) => {
      await rec.focus(await box(page.locator("main").first()), 4, 0, { overview: true });
      await rec.wait(1500);
      await rec.focus(union(await box(title), await box(create)), 4, 16);
      await rec.wait(2500);
      await moveTo(page, create);
      await rec.wait(1500);
    });
  },

  // --- Il To-Be

  "12-ipotesi": async (page, lang, id) => {
    await page.goto(`${P}?view=tobe`);
    const first = page.getByText(lang === "it" ? /nasce completa/ : /complete/i).first();
    await expect(first).toBeVisible();
    await page.waitForTimeout(800);
    await calm(page);
    const second = page.getByText(lang === "it" ? /Una delega/ : /deputy|delegat/i).first();
    await record(page, id, async (rec) => {
      await rec.focus(await box(page.locator("main").first()), 4, 0, { overview: true });
      await rec.wait(1200);
      await rec.focus(union(await box(first), await box(second)), 4, 120);
      await moveTo(page, first);
      await rec.wait(2000);
      await moveTo(page, second);
      await rec.wait(2000);
    });
  },

  // --- La consegna

  "14-pronto": async (page, lang, id) => {
    await page.goto(`${P}/handover`);
    const title = page.getByText(UI[lang].ready, { exact: true }).first();
    await expect(title).toBeVisible();
    await page.waitForTimeout(800);
    await calm(page);
    await record(page, id, async (rec) => {
      await rec.focus(await box(page.locator("main").first()), 4, 0, { overview: true });
      await rec.wait(1500);
      const list = page.locator(".handover-readiness, [data-handover-readiness]").first();
      const area = (await list.count()) ? await box(list) : union(await box(title), { ...(await box(title)), y: (await box(title)).y + 420 });
      await rec.focus(area, 4, 16);
      await rec.wait(4500);
    });
  },

  "16-cruscotto": async (page, lang, id) => {
    await page.goto(`${P}/handover/dashboard`);
    const heading = page.getByRole("heading").first();
    await expect(heading).toBeVisible();
    await page.waitForTimeout(800);
    await calm(page);
    await record(page, id, async (rec) => {
      const top = await box(page.locator("main, body").first());
      await rec.focus({ x: top.x, y: 0, width: Math.min(top.width, 1000), height: 620 }, 4, 0, { overview: true });
      await rec.wait(1800);
      // Lettura lenta: i passi del processo, con quello che cambia.
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
      await rec.focus(await box(banner), 4, 16);
      await rec.wait(1200);
      await clickOn(page, approve);
      const dialog = page.getByRole("dialog");
      if (await dialog.isVisible().catch(() => false)) {
        await rec.focus(await box(dialog), 4, 16);
        await rec.wait(1200);
        await clickOn(page, dialog.getByRole("button").last());
      }
      await rec.wait(600);
      await moveTo(page, { x: -10, y: -10 }, 10);
      await rec.focus(await box(banner), 4, 16);
      await rec.wait(3000);
    });
  },

  // --- Tutto resta

  "18-ritrova": async (page, lang, id) => {
    await page.goto("/models");
    const table = page.getByRole("table").first();
    await expect(table).toBeVisible();
    await page.waitForTimeout(800);
    await calm(page);
    await record(page, id, async (rec) => {
      await rec.focus(await box(table), 4, 24);
      await rec.wait(2500);
      await page.keyboard.press("Control+k");
      const dialog = page.getByRole("dialog");
      await rec.waitUntil(() => dialog.isVisible());
      await rec.focus(await box(dialog), 4, 24);
      await typeHuman(page, dialog.getByRole("textbox").first(), UI[lang].search);
      await moveTo(page, { x: -10, y: -10 }, 10);
      await rec.wait(800);
      await rec.focus(await box(dialog), 4, 16);
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

// --- Le scritte del film, a 1920x1080: targhette, cartelli dei capitoli, apertura e chiusura.

const tagHtml = (number: number, text: string, size = 36) => `<div style="position:fixed;left:${size}px;top:${size}px;display:flex;align-items:center;gap:${size * 0.4}px;
  padding:${size * 0.38}px ${size * 0.75}px ${size * 0.38}px ${size * 0.38}px;border-radius:999px;background:#004580;color:#fff;
  box-shadow:0 ${size * 0.3}px ${size}px -${size * 0.4}px rgba(0,30,70,.55);font:600 ${size}px/1.2 'Hanken Grotesk',system-ui,sans-serif">
  <span style="display:grid;place-items:center;width:${size * 1.35}px;height:${size * 1.35}px;border-radius:999px;background:#fff;color:#004580;font-weight:700">${number}</span>
  <span>${text}</span></div>`;

const cardHtml = (eyebrow: string, title: string, line: string) => `<div style="position:fixed;inset:0;background:#0B1021;color:#fff;display:flex;flex-direction:column;justify-content:center;padding:0 160px;
  font-family:'Hanken Grotesk',system-ui,sans-serif">
  ${eyebrow ? `<div style="font:600 30px/1.2 inherit;color:#7FB2E5;letter-spacing:.06em;text-transform:uppercase;margin-bottom:28px">${eyebrow}</div>` : ""}
  <div style="font:700 84px/1.08 inherit;max-width:1500px">${title}</div>
  <div style="font:400 38px/1.35 inherit;color:#C9D6E6;margin-top:32px;max-width:1400px">${line}</div>
  <div style="position:absolute;left:160px;bottom:90px;font:700 40px/1 inherit">DeliR<span style="color:#0071E3">.</span></div></div>`;

test("film-overlays", async ({ page }) => {
  mkdirSync(OVERLAYS, { recursive: true });
  await page.setViewportSize({ width: 1920, height: 1080 });
  const shoot = async (html: string, name: string, transparent: boolean) => {
    await page.setContent(`<!doctype html><html><body style="margin:0;background:transparent">${html}</body></html>`);
    await page.screenshot({ path: resolve(OVERLAYS, `${name}-16x9.png`), omitBackground: transparent });
  };
  for (const lang of ["it", "en"] as const) {
    await shoot(cardHtml("", FILM_INTRO[lang].title, FILM_INTRO[lang].line), `fcard-${lang}-intro`, false);
    await shoot(cardHtml("", FILM_OUTRO[lang].title, FILM_OUTRO[lang].line), `fcard-${lang}-outro`, false);
    for (const [index, chapter] of FILM.entries()) {
      const eyebrow = `${lang === "it" ? "Capitolo" : "Chapter"} ${index + 1}`;
      await shoot(cardHtml(eyebrow, chapter.title[lang], chapter.line[lang]), `fcard-${lang}-${index + 1}`, false);
      for (const scene of chapter.scenes) await shoot(tagHtml(index + 1, scene.tag[lang]), `ftag-${lang}-${scene.id}`, true);
    }
  }
});
