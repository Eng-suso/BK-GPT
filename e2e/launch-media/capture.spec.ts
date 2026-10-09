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

import { IDS, PROCESS_OWNER } from "./demo";
import { installDemoApi, unhandled } from "./mockApi";
import { Recorder, clickOn, installCursor, moveTo, slowScroll } from "./recorder";
import storyboard from "./storyboard.json";

const OUT = resolve(process.cwd(), "artifacts", "launch-media");
const RAW = resolve(OUT, "raw");
const P = `/projects/${IDS.project}/processes/${IDS.process}`;
const HOLD = storyboard.hold * 1000;

test.skip(Boolean(process.env.CI) && process.env.DELIR_LAUNCH_MEDIA !== "1", "Generatore di media: in CI con DELIR_LAUNCH_MEDIA=1");

test.beforeEach(async ({ page }) => {
  page.setDefaultTimeout(10_000);
  await installDemoApi(page);
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

// --- Card (gancio e chiusura): HTML dentro l'app, cosi' i caratteri sono i suoi.

async function showCard(page: Page, kind: "hook" | "close"): Promise<void> {
  await page.goto("/home");
  await expect(page.getByText("Acquisti indiretti e servizi").first()).toBeVisible();
  const quotes = [
    ["Laura Conti · Ufficio Tecnico", "So che poi la parte di carta viene messa a posto dopo, ma non so da chi."],
    ["Paolo Marchetti · Manutenzione", "Se mi chiedi chi materialmente lo fa, non lo so, e non voglio dirti un nome a caso."],
    ["Francesca Neri · Acquisti", "La parte di ordine si', la faccio io."],
  ];
  const scene = storyboard.scenes.find((item) => item.card === kind)!;
  await page.evaluate(({ kind, quotes, title, disclaimer }) => {
    const css = `
      .launch-card { position: fixed; inset: 0; z-index: 2147483000; display: grid; place-items: center; background: #f8fafc; color: #0f172a; }
      .launch-card .wrap { width: 1240px; display: grid; gap: 22px; }
      .launch-card .quote { opacity: 0; transform: translateY(14px); animation: launch-in 700ms cubic-bezier(.22,1,.36,1) forwards;
        background: #fff; border: 1px solid #e2e8f0; border-radius: 18px; padding: 26px 32px; box-shadow: 0 10px 30px rgba(15,23,42,.06); }
      .launch-card .quote p { font-size: 34px; line-height: 1.3; margin: 0; letter-spacing: -0.01em; }
      .launch-card .quote small { display: block; margin-top: 10px; font-size: 18px; color: #64748b; }
      .launch-card .quote.known { border-color: #2563eb; }
      .launch-card h1 { opacity: 0; animation: launch-in 800ms cubic-bezier(.22,1,.36,1) forwards; font-size: 64px; letter-spacing: -0.03em; margin: 26px 0 0; text-align: center; }
      .launch-card .brand { opacity: 0; animation: launch-in 900ms cubic-bezier(.22,1,.36,1) forwards; font-size: 120px; font-weight: 700; color: #1d4ed8; letter-spacing: -0.04em; text-align: center; }
      .launch-card .disclaimer { position: fixed; right: 36px; bottom: 28px; font-size: 16px; color: #94a3b8; }
      @keyframes launch-in { to { opacity: 1; transform: none; } }`;
    const root = document.createElement("div");
    root.className = "launch-card";
    const style = document.createElement("style");
    style.textContent = css;
    const wrap = document.createElement("div");
    wrap.className = "wrap";
    if (kind === "hook") {
      quotes.forEach(([who, text], index) => {
        const card = document.createElement("div");
        card.className = index === 2 ? "quote known" : "quote";
        card.style.animationDelay = `${0.4 + index * 2.1}s`;
        const p = document.createElement("p");
        p.textContent = `«${text}»`;
        const small = document.createElement("small");
        small.textContent = who;
        card.append(p, small);
        wrap.append(card);
      });
      const h1 = document.createElement("h1");
      h1.textContent = title;
      h1.style.animationDelay = "7s";
      wrap.append(h1);
    } else {
      const brand = document.createElement("div");
      brand.className = "brand";
      brand.textContent = "DeliR";
      brand.style.animationDelay = "0.3s";
      const h1 = document.createElement("h1");
      h1.textContent = title;
      h1.style.animationDelay = "1.1s";
      wrap.append(brand, h1);
    }
    const note = document.createElement("div");
    note.className = "disclaimer";
    note.textContent = disclaimer;
    root.append(style, wrap, note);
    document.body.append(root);
    document.getElementById("launch-cursor")?.remove();
  }, { kind, quotes, title: scene.title!, disclaimer: storyboard.disclaimer });
}

test("01-gancio", async ({ page }) => {
  await page.goto("/home");
  const rec = new Recorder(page, resolve(RAW, "01-gancio"));
  await rec.start();
  await showCard(page, "hook");
  await page.waitForTimeout(10_000);
  await rec.stop();
});

test("13-chiusura", async ({ page }) => {
  await page.goto("/home");
  const rec = new Recorder(page, resolve(RAW, "13-chiusura"));
  await rec.start();
  await showCard(page, "close");
  await page.waitForTimeout(5_000);
  await rec.stop();
});

// --- Scene di prodotto -----------------------------------------------------

test("02-capire", async ({ page }) => {
  await scene(page, "02-capire", () => openSources(page), async () => {
    await clickOn(page, page.getByRole("tab", { name: /Fonti/ }));
    await page.waitForTimeout(900);
    await clickOn(page, page.getByText("Intervista Laura Conti").first());
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByText("citazione verificata").first()).toBeVisible();
    await page.waitForTimeout(1200);
    await moveTo(page, dialog.getByText("citazione verificata").first(), 800);
    await slowScroll(page, await scrollable(dialog), 520, 4200);
    await page.waitForTimeout(1200);
  });
});

test("03-passaggio-nascosto", async ({ page }) => {
  await scene(page, "03-passaggio-nascosto", async () => {
    await openSources(page);
    await page.getByRole("tab", { name: /Fonti/ }).click();
    await expect(page.getByText("Intervista Francesca Neri").first()).toBeVisible();
  }, async () => {
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
    await page.waitForTimeout(600);
    await moveTo(page, dialog.getByText("Divergenze (3)").first(), 700);
    await page.waitForTimeout(500);
    await moveTo(page, dialog.getByText(/non so da chi/).first(), 900);
    await page.waitForTimeout(1300);
    await moveTo(page, dialog.getByText(/la faccio io/).first(), 900);
    await page.waitForTimeout(2600);
  });
});

test("04-lacuna", async ({ page }) => {
  await scene(page, "04-lacuna", async () => {
    await page.goto(P);
    await expect(page.getByRole("button", { name: /^Decidi$/ })).toBeVisible();
  }, async () => {
    await clickOn(page, page.getByRole("button", { name: /^Decidi$/ }));
    await page.waitForTimeout(900);
    await clickOn(page, page.getByRole("button", { name: /Da decidere/ }));
    await page.waitForTimeout(700);
    await moveTo(page, page.getByText(/Qual e' la soglia di importo/).first(), 900);
    await page.waitForTimeout(1400);
    await moveTo(page, page.getByText("Chiedo la procedura scritta a Francesca"), 800);
    await page.waitForTimeout(2600);
  });
});

test("05-ogni-passaggio-una-fonte", async ({ page }) => {
  await scene(page, "05-ogni-passaggio-una-fonte", async () => {
    await page.goto(`${P}?view=canvas`);
    await expect(page.locator("[data-element-id='percorso_urgente_regolarizza_ordine']").first()).toBeVisible();
  }, async () => {
    await clickOn(page, page.getByRole("button", { name: "Evidenze" }));
    const panel = page.getByRole("complementary", { name: "Evidenze del disegno" });
    await expect(panel).toContainText("100%");
    await page.waitForTimeout(900);
    await moveTo(page, panel.getByText("Il disegno coincide con le fonti"), 800);
    await page.waitForTimeout(900);
    await clickOn(page, panel.locator("summary", { hasText: "Citati dalle fonti" }));
    await page.waitForTimeout(700);
    const quote = panel.getByText(/ricostruire la pratica a posteriori/).first();
    await quote.scrollIntoViewIfNeeded();
    await moveTo(page, quote, 900);
    await page.waitForTimeout(800);
    await moveTo(page, page.locator("[data-element-id='percorso_urgente_regolarizza_ordine']").first(), 900);
    await page.waitForTimeout(2400);
  });
});

test("06-ultima-parola", async ({ page }) => {
  await scene(page, "06-ultima-parola", async () => {
    await page.goto(`${P}?view=canvas`);
    await expect(page.getByRole("button", { name: "Importa, esporta, cronologia" })).toBeVisible();
  }, async () => {
    await clickOn(page, page.getByRole("button", { name: "Importa, esporta, cronologia" }));
    await page.waitForTimeout(500);
    await clickOn(page, page.getByRole("menuitem", { name: /Cronologia versioni/ }));
    await page.waitForTimeout(800);
    await moveTo(page, page.getByText("As-Is v3 · validato con Laura Conti").first(), 900);
    await page.waitForTimeout(3200);
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
  }, async () => {
    await clickOn(page, page.getByRole("button", { name: "Riproduci", exact: true }), 600);
    await moveTo(page, { x: 960, y: 1040 }, 500);
    await page.waitForTimeout(12_500);
  });
}

test("07-simula-as-is", async ({ page }) => replayScene(page, "07-simula-as-is", IDS.asIsRun));
test("09-simula-to-be", async ({ page }) => replayScene(page, "09-simula-to-be", IDS.toBeRun));

test("08-to-be", async ({ page }) => {
  await scene(page, "08-to-be", async () => {
    await page.goto(P);
    await expect(page.getByRole("tab", { name: "Ipotesi To-Be" })).toBeVisible();
  }, async () => {
    await clickOn(page, page.getByRole("tab", { name: "Ipotesi To-Be" }));
    await expect(page.getByText("La richiesta nasce completa, con i campi obbligatori")).toBeVisible();
    await page.waitForTimeout(700);
    await moveTo(page, page.getByText(/Un posto unico dove la richiesta/).first(), 900);
    await page.waitForTimeout(1800);
    await moveTo(page, page.getByText(/vorrei che l'autorizzazione/).first(), 900);
    await page.waitForTimeout(2600);
  });
});

test("10-decidi", async ({ page }) => {
  await scene(page, "10-decidi", async () => {
    await page.goto(`${P}/simulation/compare?a=${IDS.asIsRun}&b=${IDS.toBeRun}`);
    await expect(page.getByText(/attraversamento −/)).toBeVisible();
    await page.getByRole("button", { name: "Mostra tutta la tela" }).click();
  }, async () => {
    await moveTo(page, page.getByText(/attraversamento −/), 1000);
    await page.waitForTimeout(1800);
    await moveTo(page, page.locator("[data-element-id='percorso_autorizzazione_autorizza_spesa']").first(), 1000);
    await page.waitForTimeout(3000);
  });
});

test("11-process-owner", async ({ page }) => {
  await scene(page, "11-process-owner", async () => {
    await page.goto(`/projects/${IDS.project}`);
    await expect(page.getByText(`Validazione del To-Be con ${PROCESS_OWNER}`)).toBeVisible();
  }, async () => {
    await moveTo(page, page.getByText("Validazione del process owner").first(), 900);
    await page.waitForTimeout(1400);
    await moveTo(page, page.getByText(`Validazione del To-Be con ${PROCESS_OWNER}`), 900);
    await page.waitForTimeout(2800);
  });
});

test("12-memoria", async ({ page }) => {
  await scene(page, "12-memoria", async () => {
    await page.goto(`/projects/${IDS.project}`);
    await expect(page.getByRole("tab", { name: /Fonti/ })).toBeVisible();
  }, async (rec) => {
    const nav = (name: string) => page.getByRole("button", { name, exact: true }).first();
    await clickOn(page, nav("Clienti"));
    await page.waitForTimeout(1200);
    await clickOn(page, page.getByText("Vetrano Industriale S.p.A.").first());
    await page.waitForTimeout(1800);
    await clickOn(page, nav("Home"));
    rec.mark("portfolio");
    await page.waitForTimeout(3600);
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
  const font = await page.evaluate(() => getComputedStyle(document.body).fontFamily);
  const texts: Record<string, string> = { disclaimer: storyboard.disclaimer };
  for (const item of storyboard.scenes) {
    if (item.caption) texts[`${item.id}`] = item.caption;
    (item.captions ?? []).forEach((extra, index) => { texts[`${item.id}-${index + 1}`] = extra.text; });
  }
  for (const [name, text] of Object.entries(texts)) {
    await page.setContent(`<!doctype html><html><body style="margin:0;background:transparent;font-family:${font.replace(/"/g, "'")}">
      <div style="position:fixed;inset:0;display:flex;align-items:${name === "disclaimer" ? "flex-end" : "flex-end"};justify-content:${name === "disclaimer" ? "flex-end" : "center"};padding:${name === "disclaimer" ? "0 28px 22px 0" : "0 0 120px 0"}">
        <div style="${name === "disclaimer"
          ? "font-size:15px;color:#64748b;background:rgba(255,255,255,.88);border:1px solid #e2e8f0;border-radius:999px;padding:6px 14px"
          : "font-size:52px;font-weight:600;letter-spacing:-0.02em;color:#fff;background:rgba(15,23,42,.88);border-radius:22px;padding:26px 44px;box-shadow:0 20px 60px rgba(15,23,42,.35);max-width:1500px;text-align:center"}">${text.replace(/&/g, "&amp;").replace(/</g, "&lt;")}</div>
      </div></body></html>`);
    await page.screenshot({ path: resolve(dir, `${name}.png`), omitBackground: true });
  }
});
