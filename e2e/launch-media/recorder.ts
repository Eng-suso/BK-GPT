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

type Rect = { x: number; y: number; width: number; height: number };

async function rectOf(target: Locator | Rect): Promise<Rect | null> {
  return "boundingBox" in target ? target.boundingBox() : target;
}

/** Il corpo del testo visibile piu' piccolo dentro un rettangolo (px CSS). */
function smallestText(area: Rect): number | null {
  let smallest: number | null = null;
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const parent = node.parentElement;
    if (!parent || !node.textContent?.trim()) continue;
    const range = document.createRange();
    range.selectNodeContents(node);
    const r = range.getBoundingClientRect();
    if (r.width === 0 || r.right < area.x || r.left > area.x + area.width || r.bottom < area.y || r.top > area.y + area.height) continue;
    const style = getComputedStyle(parent);
    if (style.visibility === "hidden") continue;
    // Testo nascosto da un antenato trasparente (es. elementi che entrano dopo).
    let hidden = false;
    for (let el: Element | null = parent; el && el !== document.body; el = el.parentElement) {
      if (Number(getComputedStyle(el).opacity) === 0) { hidden = true; break; }
    }
    if (hidden) continue;
    // Nel canvas BPMN il testo e' SVG scalato dallo zoom: conta l'altezza disegnata.
    const svg = parent.closest("svg");
    const size = svg ? r.height / 1.2 : parseFloat(style.fontSize);
    smallest = smallest === null ? size : Math.min(smallest, size);
  }
  return smallest;
}

const SCREENCAST_SCALE = Number(process.env.LAUNCH_SCREENCAST_SCALE ?? 1);

export class Recorder {
  private session: CDPSession | null = null;
  protected frames: { file: string; t: number }[] = [];
  protected marks: Record<string, number> = {};
  protected camera: { t: number; rect: Rect | null; zoom?: number; narrow?: Rect; minFont?: number | null; overview?: boolean }[] = [];
  protected started = 0;
  private pending: Promise<unknown>[] = [];

  constructor(protected readonly page: Page, protected readonly dir: string) {}

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
      // Qualita' e scala regolabili: a piena densita' i fotogrammi pesano e ne
      // arrivano meno al secondo (le palline della simulazione andrebbero a scatti).
      format: "jpeg", quality: Number(process.env.LAUNCH_SCREENCAST_QUALITY ?? 92),
      maxWidth: Math.round(width * dpr * SCREENCAST_SCALE), maxHeight: Math.round(height * dpr * SCREENCAST_SCALE), everyNthFrame: 1,
    });
    this.started = Date.now() / 1000;
    // Un primo fotogramma anche se la pagina e' ferma.
    await this.page.evaluate(() => document.body.style.setProperty("--launch-tick", String(Math.random())));
  }

  /** Secondi dall'inizio della ripresa. */
  protected now(): number {
    return Date.now() / 1000 - this.started;
  }

  /** Attesa dentro la ripresa (tempo reale; il registratore virtuale cattura). */
  async wait(ms: number): Promise<void> {
    await this.page.waitForTimeout(ms);
  }

  /** Attende una condizione della pagina, al massimo `maxMs`. */
  async waitUntil(condition: () => Promise<boolean>, maxMs = 3000): Promise<void> {
    for (let waited = 0; waited < maxMs && !(await condition()); waited += 50) await this.wait(50);
  }

  mark(name: string): void {
    this.marks[name] = this.now();
  }

  /**
   * Inquadratura: il montaggio (scripts/launch_media_edit.py) porta la camera
   * su questo rettangolo, con un movimento morbido. `zoom` e' il massimo.
   *
   * Opzioni del piano video (scripts/launch_media_montage.py):
   * - `narrow`: l'area da tenere nel formato 4:5 del telefono, se diversa;
   * - il testo piu' piccolo dentro l'area (`minFont`, px CSS), per verificare
   *   che a schermo non scenda sotto gli 11 px;
   * - `overview`: colpo d'insieme per orientarsi (al massimo 2 s, testo libero).
   */
  async focus(
    target: Locator | Rect,
    zoom = 1.6,
    pad = 48,
    options: { narrow?: Locator | Rect; narrowPad?: number; overview?: boolean } = {},
  ): Promise<void> {
    const box = await rectOf(target);
    if (!box) return;
    const narrowBox = options.narrow ? await rectOf(options.narrow) : null;
    const padded = (r: Rect, p: number) => ({ x: r.x - p, y: r.y - p, width: r.width + 2 * p, height: r.height + 2 * p });
    const rect = padded(box, pad);
    const narrow = narrowBox ? padded(narrowBox, options.narrowPad ?? pad) : null;
    // Un colpo d'insieme serve a orientarsi: niente verifica del testo, ma il
    // montaggio lo tiene al massimo 2 s (piano video).
    const minFont = options.overview ? null : await this.page.evaluate(smallestText, narrow ?? rect).catch(() => null);
    this.camera.push({ t: this.now(), rect, zoom, ...(narrow ? { narrow } : {}), minFont, ...(options.overview ? { overview: true } : {}) });
  }

  /** Ritorno al campo largo. */
  wide(): void {
    this.camera.push({ t: this.now(), rect: null });
  }

  /** Il logo bpmn.io resta nel prodotto (licenza) ma non entra mai in quadro. */
  protected async forbiddenZones(): Promise<Rect[]> {
    return this.page.evaluate(() =>
      [...document.querySelectorAll(".bjs-powered-by")]
        .map((el) => el.getBoundingClientRect())
        .filter((r) => r.width > 0 && r.height > 0)
        .map((r) => ({ x: r.left, y: r.top, width: r.width, height: r.height })),
    ).catch(() => []);
  }

  async stop(): Promise<void> {
    const ended = Date.now() / 1000;
    const forbidden = await this.forbiddenZones();
    await this.session?.send("Page.stopScreencast");
    await Promise.all(this.pending);
    await this.session?.detach();
    const t0 = this.frames[0]?.t ?? this.started;
    const events = cues
      .filter((item) => item.at >= this.started && item.at <= ended)
      .map(({ at, ...item }) => ({ ...item, t: at - this.started }));
    writeFileSync(
      resolve(this.dir, "scene.json"),
      JSON.stringify({ duration: ended - this.started, offset: t0 - this.started, frames: this.frames.map((f) => ({ ...f, t: f.t - t0 })), marks: this.marks, camera: this.camera, events, viewport: this.page.viewportSize(), forbidden, end: ended - t0 }, null, 1),
    );
  }
}

/** Il registratore virtuale attivo: i gesti del cursore avanzano il suo tempo. */
let virtual: VirtualRecorder | null = null;

/** Un'attesa nei gesti: tempo reale, o fotogrammi se la ripresa e' virtuale. */
export async function pause(page: Page, ms: number): Promise<void> {
  if (virtual) await virtual.wait(ms);
  else await page.waitForTimeout(ms);
}

/** Avanza le animazioni CSS e Web della pagina di un passo (in pausa fra i passi). */
function stepAnimations(stepMs: number): void {
  for (const animation of document.getAnimations()) {
    if (animation.playState === "finished") continue;
    animation.pause();
    const next = (Number(animation.currentTime) || 0) + stepMs;
    const end = animation.effect?.getComputedTiming().endTime;
    if (typeof end === "number" && Number.isFinite(end) && next >= end) animation.finish();
    else animation.currentTime = next;
  }
}

/**
 * Ripresa a tempo virtuale: l'orologio della pagina (Playwright `page.clock`,
 * che governa timer, requestAnimationFrame e performance) e le animazioni CSS
 * avanzano di 1/30 di secondo, poi si scatta il fotogramma. Il video e' nitido
 * alla densita' piena e fluido a 30 fps esatti, qualunque sia la velocita'
 * della macchina: senza GPU lo screencast a densita' 2 arriva a 13 fps.
 *
 * Richiede `page.clock.install()` prima di aprire la pagina; fuori dalla
 * ripresa il tempo scorre normale.
 */
export class VirtualRecorder extends Recorder {
  private t = 0;
  private readonly step: number;

  constructor(page: Page, dir: string, private readonly fps = 30) {
    super(page, dir);
    this.step = 1000 / fps;
  }

  protected override now(): number {
    return this.t;
  }

  override async start(): Promise<void> {
    rmSync(this.dir, { recursive: true, force: true });
    mkdirSync(resolve(this.dir, "frames"), { recursive: true });
    const now = await this.page.evaluate(() => Date.now());
    await this.page.clock.pauseAt(now + 20);
    virtual = this;
    await this.shoot();
  }

  private async shoot(): Promise<void> {
    const file = `frames/f${String(this.frames.length).padStart(5, "0")}.jpg`;
    writeFileSync(resolve(this.dir, file), await this.page.screenshot({ type: "jpeg", quality: 92 }));
    this.frames.push({ file, t: this.t });
  }

  override async wait(ms: number): Promise<void> {
    for (let i = 0; i < Math.max(1, Math.round(ms / this.step)); i++) {
      await this.page.clock.runFor(this.step);
      await this.page.evaluate(stepAnimations, this.step);
      this.t += 1 / this.fps;
      await this.shoot();
    }
  }

  override async waitUntil(condition: () => Promise<boolean>, maxMs = 3000): Promise<void> {
    for (let waited = 0; waited < maxMs && !(await condition()); waited += this.step) await this.wait(this.step);
  }

  override async stop(): Promise<void> {
    const forbidden = await this.forbiddenZones();
    virtual = null;
    await this.page.clock.resume();
    writeFileSync(
      resolve(this.dir, "scene.json"),
      JSON.stringify({ duration: this.t, offset: 0, frames: this.frames, marks: this.marks, camera: this.camera, events: [], viewport: this.page.viewportSize(), forbidden, end: this.t }, null, 1),
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

/** Movimenti da 1,2 s (piano video): chi guarda segue il gesto. */
export async function moveTo(page: Page, target: Locator | { x: number; y: number }, ms = 1200): Promise<void> {
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
  await pause(page, ms + 60);
}

export async function clickOn(page: Page, target: Locator, ms = 1200): Promise<void> {
  await moveTo(page, target, ms);
  await page.evaluate(() => document.getElementById("launch-cursor")?.classList.add("is-clicking"));
  cue("click");
  await pause(page, 140);
  // A tempo virtuale i controlli di stabilita' di Playwright aspetterebbero
  // fotogrammi che non arrivano: il bersaglio e' gia' stato raggiunto.
  await target.click({ force: Boolean(virtual) });
  await page.evaluate(() => document.getElementById("launch-cursor")?.classList.remove("is-clicking"));
  await pause(page, 260);
}

/** Scrittura a ritmo umano: circa 70 ms per carattere (piano video). */
export async function typeHuman(page: Page, target: Locator, text: string, msPerChar = 70): Promise<void> {
  await clickOn(page, target);
  cue("typing", { length: text.length });
  await target.pressSequentially(text, { delay: msPerChar });
}

/** Scorrimento lento di un contenitore, a passi, come una lettura. */
export async function slowScroll(page: Page, container: Locator, pixels: number, ms: number): Promise<void> {
  const steps = Math.max(1, Math.round(ms / 50));
  for (let i = 0; i < steps; i++) {
    await container.evaluate((el, dy) => el.scrollBy({ top: dy }), pixels / steps);
    await pause(page, 50);
  }
}
