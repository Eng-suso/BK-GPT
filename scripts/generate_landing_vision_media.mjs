import { chromium } from "playwright";
import { mkdir, copyFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const ROOT = resolve(process.cwd(), "artifacts", "landing-media", "vision");
const SOURCE = resolve(ROOT, "source", "product-vision.html");
const IMAGES = resolve(ROOT, "images");
const VIDEOS = resolve(ROOT, "videos");
const RECORDING = resolve(ROOT, "recording");

await Promise.all([IMAGES, VIDEOS, RECORDING].map((path) => mkdir(path, { recursive: true })));

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 1 });
await page.goto(pathToFileURL(SOURCE).href);

const shots = [
  ["memory", "01-company-memory-temporal-provenance.png"],
  ["systems", "02-management-system-engine.png"],
  ["impact", "03-change-impact-analysis.png"],
  ["architecture", "04-memory-under-the-operating-loop.png"],
];

for (const [scene, filename] of shots) {
  await page.evaluate((id) => window.showScene(id), scene);
  await page.waitForTimeout(520);
  if (scene === "memory") {
    await page.locator('[data-change="new"]').click();
    await page.waitForTimeout(900);
  }
  if (scene === "impact") await page.waitForTimeout(900);
  await page.screenshot({ path: resolve(IMAGES, filename), fullPage: false });
}
await browser.close();

const videoBrowser = await chromium.launch({ headless: true });
const context = await videoBrowser.newContext({
  viewport: { width: 1600, height: 1000 },
  recordVideo: { dir: RECORDING, size: { width: 1600, height: 1000 } },
});
const videoPage = await context.newPage();
await videoPage.goto(pathToFileURL(SOURCE).href);
await videoPage.evaluate(() => window.resetVision());

const cursor = videoPage.locator("#demo-cursor");
await cursor.evaluate((el) => el.classList.add("visible"));

async function pointAndClick(locator, travel = 520) {
  const box = await locator.boundingBox();
  if (!box) return;
  await cursor.evaluate((el, pos) => {
    el.style.left = `${pos.x}px`;
    el.style.top = `${pos.y}px`;
  }, { x: box.x + box.width / 2, y: box.y + box.height / 2 });
  await videoPage.waitForTimeout(travel + 90);
  await cursor.evaluate((el) => el.classList.add("clicking"));
  await videoPage.waitForTimeout(130);
  await locator.click();
  await cursor.evaluate((el) => el.classList.remove("clicking"));
  await videoPage.waitForTimeout(450);
}

await videoPage.waitForTimeout(1300);
await pointAndClick(videoPage.locator('[data-change="new"]'), 700);
await videoPage.waitForTimeout(2600);
await pointAndClick(videoPage.locator('[data-scene="systems"]'), 800);
await videoPage.waitForTimeout(1700);
await pointAndClick(videoPage.locator('[data-pack="9001"]'), 650);
await videoPage.waitForTimeout(2100);
await pointAndClick(videoPage.locator('[data-scene="impact"]'), 800);
await videoPage.waitForTimeout(3600);
await pointAndClick(videoPage.locator('[data-scene="architecture"]'), 800);
await videoPage.waitForTimeout(3000);

const video = videoPage.video();
await context.close();
if (video) await video.saveAs(resolve(VIDEOS, "01-memory-compliance-impact-vision.webm"));
await videoBrowser.close();

await copyFile(
  resolve(IMAGES, "01-company-memory-temporal-provenance.png"),
  resolve(ROOT, "poster-memory-compliance-impact.png"),
);

console.log(`Generated landing vision media in ${ROOT}`);
