/**
 * La clip social da 45 s in inglese (taglio `social-45-en` di storyboard.json):
 * i testi a schermo e i due cartelli, apertura e chiusura. Le riprese del
 * prodotto sono quelle inglesi del caso semplice (`clips.spec.ts`, `s-en-*`).
 *
 *   DELIR_CLIP_LANGS=en npx playwright test -c playwright.launch.config.ts simple/clips simple/social
 *   python3 scripts/launch_media_edit.py social-45-en
 *
 * Nel feed la clip parte muta: ogni ripresa ha una frase, in basso al centro.
 */
import { expect, test, type Page } from "@playwright/test";
import { resolve } from "node:path";

import { Recorder } from "../recorder";
import { simpleCase } from "./case";
import { installSimpleApi } from "./mockApi";

const ROOT = resolve(process.cwd(), "artifacts", "launch-media");
const EASE = "cubic-bezier(.22,1,.36,1)";

/** Le frasi delle riprese: chiave = nome dell'overlay usato nel taglio. */
export const SOCIAL_CAPTIONS: Record<string, string> = {
  "social-en-discovery": "Upload the interviews. DeliR maps how the work really gets done.",
  "social-en-fonti": "Every statement keeps the exact quote it came from.",
  "social-en-evidenze": "Every step of the process is backed by a source.",
  "social-en-replay-as-is": "Simulate today’s process and watch where work piles up.",
  "social-en-heatmap": "The bottleneck, measured: requests wait for the manager’s sign-off.",
  "social-en-replay-to-be": "Test the change first: a delegate signs every day. Cycle time −61%.",
  "social-en-consegna": "Hand over the change, the reason and the simulated numbers.",
};

const CARDS = {
  "social-en-intro": {
    kicker: "DeliR",
    lines: ["Understand how a business really operates.", "Simulate a decision before you make it."],
    foot: "",
  },
  "social-en-outro": {
    kicker: "DeliR",
    lines: ["From interviews to a decision you can defend."],
    foot: "Building in public · delir.it",
  },
} as const;

test.skip(Boolean(process.env.CI) && process.env.DELIR_LAUNCH_MEDIA !== "1", "Generatore di media: in CI con DELIR_LAUNCH_MEDIA=1");
test.use({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1.5 });

async function productFont(page: Page): Promise<string> {
  const demo = simpleCase("en");
  await installSimpleApi(page, demo);
  await page.goto("/home");
  await expect(page.getByText(demo.client).first()).toBeVisible();
  return (await page.evaluate(() => getComputedStyle(document.body).fontFamily)).replace(/"/g, "'");
}

function escape(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;");
}

test("social-en captions", async ({ page }) => {
  const font = await productFont(page);
  await page.setViewportSize({ width: 1920, height: 1080 });
  for (const [name, text] of Object.entries(SOCIAL_CAPTIONS)) {
    await page.setContent(`<!doctype html><html><body style="margin:0;background:transparent;font-family:${font}">
      <div style="position:fixed;left:50%;bottom:78px;transform:translateX(-50%);max-width:1500px;width:max-content;box-sizing:border-box;
        padding:18px 34px;border-radius:22px;background:rgba(15,23,42,.92);color:#fff;text-align:center;
        font-size:44px;line-height:1.25;font-weight:600;letter-spacing:-0.012em;box-shadow:0 18px 50px -20px rgba(15,23,42,.6)">${escape(text)}</div></body></html>`);
    await page.screenshot({ path: resolve(ROOT, "overlays", `${name}.png`), omitBackground: true });
  }
});

for (const [id, card] of Object.entries(CARDS)) {
  test(id, async ({ page }) => {
    const font = await productFont(page);
    const lines = card.lines.map((line, index) => `<p class="l" style="transition-delay:${250 + index * 450}ms">${escape(line)}</p>`).join("");
    await page.setContent(`<!doctype html><html><head><style>
      html,body{margin:0;height:100%}
      body{display:grid;place-items:center;background:radial-gradient(1200px 600px at 50% 40%,#ffffff 0%,#eef2f8 70%);font-family:${font};color:#0f172a}
      .w{text-align:center;max-width:1040px;padding:0 40px}
      .k{display:inline-flex;align-items:center;gap:10px;font-size:30px;font-weight:700;letter-spacing:-0.02em;margin-bottom:34px}
      .k i{width:12px;height:12px;border-radius:50%;background:#1d63ed}
      .l{margin:0 0 14px;font-size:50px;line-height:1.15;font-weight:650;letter-spacing:-0.025em}
      .f{margin-top:34px;font-size:22px;color:#475569;font-weight:500}
      .k,.l,.f{opacity:0;transform:translateY(16px);transition:opacity 700ms ${EASE},transform 700ms ${EASE}}
      .in .k,.in .l,.in .f{opacity:1;transform:none}
      .f{transition-delay:${250 + card.lines.length * 450}ms}
    </style></head><body><div class="w"><div class="k"><i></i>${card.kicker}</div>${lines}${card.foot ? `<p class="f">${escape(card.foot)}</p>` : ""}</div></body></html>`);
    await page.evaluate(() => document.fonts.ready);
    const rec = new Recorder(page, resolve(ROOT, "raw", id));
    await rec.start();
    await page.waitForTimeout(150);
    await page.evaluate(() => document.body.classList.add("in"));
    await page.waitForTimeout(3600);
    await rec.stop();
  });
}
