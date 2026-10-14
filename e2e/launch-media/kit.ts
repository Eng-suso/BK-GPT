/**
 * Gli attrezzi comuni alle riprese dei video (hero e film): riquadri, la
 * ripresa a tempo virtuale, la pulizia della pagina prima di girare.
 */
import type { Locator, Page } from "@playwright/test";
import { resolve } from "node:path";

import { VirtualRecorder } from "./recorder";

export const RAW = resolve(process.cwd(), "artifacts", "launch-media", "raw");
export const OVERLAYS = resolve(process.cwd(), "artifacts", "launch-media", "overlays");
export const EASE = "cubic-bezier(.22,1,.36,1)";

export type Rect = { x: number; y: number; width: number; height: number };

export async function box(target: Locator): Promise<Rect> {
  const found = await target.boundingBox();
  if (!found) throw new Error(`nessun riquadro per ${target}`);
  return found;
}

export function union(...rects: Rect[]): Rect {
  const x = Math.min(...rects.map((r) => r.x));
  const y = Math.min(...rects.map((r) => r.y));
  return { x, y, width: Math.max(...rects.map((r) => r.x + r.width)) - x, height: Math.max(...rects.map((r) => r.y + r.height)) - y };
}

/** Toglie caret e outline di focus rimasti dalla preparazione. */
export async function calm(page: Page): Promise<void> {
  // Niente menu contestuale di bpmn-js sul nodo selezionato: in video e' rumore.
  await page.addStyleTag({ content: "*:focus, *:focus-visible { outline: none !important; box-shadow: none !important; } * { caret-color: transparent !important; } .djs-context-pad, .djs-popup { display: none !important; }" });
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
}

/** Ripresa a tempo virtuale: nitida a densita' piena e a 30 fps esatti. */
export async function record(page: Page, id: string, act: (rec: VirtualRecorder) => Promise<void>): Promise<void> {
  const rec = new VirtualRecorder(page, resolve(RAW, id));
  await rec.start();
  await act(rec);
  await rec.stop();
}
