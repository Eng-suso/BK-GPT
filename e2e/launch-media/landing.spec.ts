/**
 * La landing con il video hero: parte da solo, fa il loop, si ferma con
 * "riduci movimento", sta nello schermo del telefono.
 */
import { expect, test, type Page } from "@playwright/test";
import { resolve } from "node:path";

const URL = "http://127.0.0.1:4310/index.html";
const OUT = resolve(process.cwd(), "artifacts", "launch-media", "landing-check");

test.skip(Boolean(process.env.CI) && process.env.DELIR_LAUNCH_MEDIA !== "1", "Generatore di media: in CI con DELIR_LAUNCH_MEDIA=1");

const state = (page: Page) => page.locator(".hero-video").evaluate((v: HTMLVideoElement) => ({
  paused: v.paused, time: v.currentTime, ready: v.readyState, duration: v.duration, src: v.currentSrc,
}));

test("desktop: il video parte da solo e fa il loop senza fermarsi", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(URL);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Process Intelligence Software for Efficient and Effective Operations");
  await expect.poll(async () => (await state(page)).time, { timeout: 10_000 }).toBeGreaterThan(0.5);
  const first = await state(page);
  expect(first.paused).toBe(false);
  expect(first.duration).toBeGreaterThan(8);
  expect(first.duration).toBeLessThan(16);
  // Il loop: il tempo torna indietro senza che il video si fermi.
  let looped = false;
  let last = first.time;
  for (let i = 0; i < 30 && !looped; i += 1) {
    await page.waitForTimeout(500);
    const now = await state(page);
    expect(now.paused).toBe(false);
    if (now.time < last) looped = true;
    last = now.time;
  }
  expect(looped).toBe(true);
  // Il video sta nella prima schermata.
  const box = (await page.locator(".hero-video").boundingBox())!;
  expect(box.y + box.height).toBeLessThanOrEqual(900);
  await page.screenshot({ path: resolve(OUT, "desktop-1440.png") });
});

test("mobile: niente scorrimento orizzontale, video intero sotto il testo", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(URL);
  await expect.poll(async () => (await state(page)).time, { timeout: 10_000 }).toBeGreaterThan(0.3);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  const box = (await page.locator(".hero-video").boundingBox())!;
  expect(box.x).toBeGreaterThanOrEqual(15);
  expect(box.x + box.width).toBeLessThanOrEqual(390 - 15);
  await page.locator(".hero-video").scrollIntoViewIfNeeded();
  await page.screenshot({ path: resolve(OUT, "mobile-390.png"), fullPage: true });
});

test("riduci movimento: resta il poster, il video non parte", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(URL);
  await page.waitForTimeout(1500);
  const now = await state(page);
  expect(now.paused).toBe(true);
  expect(now.time).toBe(0);
});
