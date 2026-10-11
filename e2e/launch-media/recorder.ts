import type { CDPSession, Locator, Page } from "@playwright/test";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

/**
 * Registrazione fotogramma per fotogramma con il screencast di Chromium (CDP).
 *
 * Il `recordVideo` di Playwright comprime in VP8 a bitrate basso: per una
 * landing serve nitidezza. Qui ogni fotogramma ridisegnato arriva come JPEG con
 * il suo istante; il montaggio (`scripts/launch_media_render.mjs`) li porta a
 * 30 fps costanti. I `mark` segnano istanti della scena per i testi a schermo.
 */
/**
 * Eventi sonori (clic, digitazione, card che entrano): li scrivono i gesti
 * del cursore e le card; ogni scena tiene quelli caduti durante la sua
 * registrazione. Il montaggio (`launch_media_edit.py`) ci mette gli effetti.
 */
type Cue = { at: number; kind: string; count?: number; length?: number };
const cues: Cue[] = [];

export function cue(kind: string, extra: { count?: number; length?: number } = {}, delay = 0): void {
  cues.push({ at: Date.now() / 1000 + delay, kind, ...extra });
}

export class Recorder {
  private session: CDPSession | null = null;
  private frames: { file: string; t: number }[] = [];
  private marks: Record<string, number> = {};
  private camera: { t: number; rect: { x: number; y: number; width: number; height: number } | null; zoom?: number }[] = [];
  private started = 0;
  private pending: Promise<unknown>[] = [];

  constructor(private readonly page: Page, private readonly dir: string) {}

  async start(): Promise<void> {
    rmSync(this.dir, { recursive: true, force: true });
    mkdirSync(resolve(this.dir, "frames"), { recursive: true });
    this.session = await this.page.context().newCDPSession(this.page);
    this.session.on("Page.screencastFrame", ({ data, metadata, sessionId }) => {
      const file = `frames/f${String(this.frames.length).padStart(5, "0")}.jpg`;
      this.frames.push({ file, t: metadata.timestamp ?? Date.now() / 1000 });
      writeFileSync(resolve(this.dir, file), Buffer.from(data, "base64"));
      this.pending.push(this.session!.send("Page.screencastFrameAck", { sessionId }).catch(() => undefined));
    });
    const { width, height } = this.page.viewportSize() ?? { width: 1920, height: 1080 };
    // Con densita' > 1 (scene ravvicinate) i fotogrammi restano a piena risoluzione.
    const dpr = await this.page.evaluate(() => window.devicePixelRatio);
    await this.session.send("Page.startScreencast", {
      format: "jpeg", quality: 92, maxWidth: Math.round(width * dpr), maxHeight: Math.round(height * dpr), everyNthFrame: 1,
    });
    this.started = Date.now() / 1000;
    // Un primo fotogramma anche se la pagina e' ferma.
    await this.page.evaluate(() => document.body.style.setProperty("--launch-tick", String(Math.random())));
  }

  mark(name: string): void {
    this.marks[name] = Date.now() / 1000 - this.started;
  }

  /**
   * Inquadratura: il montaggio (scripts/launch_media_edit.py) porta la camera
   * su questo rettangolo, con un movimento morbido. `zoom` e' il massimo.
   */
  async focus(target: Locator | { x: number; y: number; width: number; height: number }, zoom = 1.6, pad = 48): Promise<void> {
    const box = "boundingBox" in target ? await target.boundingBox() : target;
    if (!box) return;
    this.camera.push({
      t: Date.now() / 1000 - this.started,
      rect: { x: box.x - pad, y: box.y - pad, width: box.width + 2 * pad, height: box.height + 2 * pad },
      zoom,
    });
  }

  /** Ritorno al campo largo. */
  wide(): void {
    this.camera.push({ t: Date.now() / 1000 - this.started, rect: null });
  }

  async stop(): Promise<void> {
    const ended = Date.now() / 1000;
    await this.session?.send("Page.stopScreencast");
    await Promise.all(this.pending);
    await this.session?.detach();
    const t0 = this.frames[0]?.t ?? this.started;
    const events = cues
      .filter((item) => item.at >= this.started && item.at <= ended)
      .map(({ at, ...item }) => ({ ...item, t: at - this.started }));
    writeFileSync(
      resolve(this.dir, "scene.json"),
      JSON.stringify({ duration: ended - this.started, offset: t0 - this.started, frames: this.frames.map((f) => ({ ...f, t: f.t - t0 })), marks: this.marks, camera: this.camera, events, viewport: this.page.viewportSize(), end: ended - t0 }, null, 1),
    );
  }
}

/** Un cursore visibile e lento: in un video muto e' il gesto del consulente. */
export async function installCursor(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const mount = () => {
      if (document.getElementById("launch-cursor")) return;
      const style = document.createElement("style");
      style.textContent = `
        #launch-cursor { position: fixed; left: 960px; top: 600px; width: 28px; height: 28px; z-index: 2147483647;
          pointer-events: none; transform: translate(-4px, -2px); transition-property: left, top;
          transition-timing-function: cubic-bezier(.22, 1, .36, 1); filter: drop-shadow(0 2px 4px rgba(15,23,42,.35)); }
        #launch-cursor::after { content: ""; position: absolute; left: -10px; top: -10px; width: 28px; height: 28px; border-radius: 999px;
          background: rgba(37, 99, 235, .25); transform: scale(0); opacity: 0; transition: transform 260ms ease, opacity 260ms ease; }
        #launch-cursor.is-clicking::after { transform: scale(1.4); opacity: 1; }`;
      const cursor = document.createElement("div");
      cursor.id = "launch-cursor";
      cursor.innerHTML = '<svg width="28" height="28" viewBox="0 0 28 28"><path d="M4 2 L4 22 L9.5 17 L13 25 L16.5 23.5 L13 15.5 L20.5 15.5 Z" fill="#0f172a" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>';
      document.documentElement.append(style, cursor);
    };
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount);
    else mount();
  });
}

export async function moveTo(page: Page, target: Locator | { x: number; y: number }, ms = 700): Promise<void> {
  let point = target as { x: number; y: number };
  if ("boundingBox" in target) {
    await target.scrollIntoViewIfNeeded().catch(() => undefined);
    const box = await target.boundingBox();
    if (!box) return;
    point = { x: box.x + Math.min(box.width / 2, 60), y: box.y + box.height / 2 };
  }
  await page.evaluate(({ x, y, ms }) => {
    const cursor = document.getElementById("launch-cursor");
    if (!cursor) return;
    cursor.style.transitionDuration = `${ms}ms`;
    cursor.style.left = `${x}px`;
    cursor.style.top = `${y}px`;
  }, { ...point, ms });
  await page.mouse.move(point.x, point.y, { steps: 6 });
  await page.waitForTimeout(ms + 60);
}

export async function clickOn(page: Page, target: Locator, ms = 700): Promise<void> {
  await moveTo(page, target, ms);
  await page.evaluate(() => document.getElementById("launch-cursor")?.classList.add("is-clicking"));
  cue("click");
  await page.waitForTimeout(140);
  await target.click();
  await page.evaluate(() => document.getElementById("launch-cursor")?.classList.remove("is-clicking"));
  await page.waitForTimeout(260);
}

/** Scorrimento lento di un contenitore, a passi, come una lettura. */
export async function slowScroll(page: Page, container: Locator, pixels: number, ms: number): Promise<void> {
  const steps = Math.max(1, Math.round(ms / 50));
  for (let i = 0; i < steps; i++) {
    await container.evaluate((el, dy) => el.scrollBy({ top: dy }), pixels / steps);
    await page.waitForTimeout(50);
  }
}
