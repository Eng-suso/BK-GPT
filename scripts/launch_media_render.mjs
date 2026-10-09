#!/usr/bin/env node
/**
 * Montaggio dei media di lancio con ffmpeg, dai fotogrammi registrati da
 * `e2e/launch-media/capture.spec.ts`.
 *
 * Esce in artifacts/launch-media/:
 *   scenes/<id>.mp4          scena del video, con testo a schermo e disclaimer
 *   landing/<nome>.mp4|webm  clip in loop per la landing (senza testo) + poster
 *   landing/hero-loop.*      il loop dell'hero (storyboard.json -> hero)
 *   video/delir-presentazione-it.mp4   il video muto completo
 *
 *   node scripts/launch_media_render.mjs
 */
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const ROOT = resolve("artifacts", "launch-media");
const RAW = resolve(ROOT, "raw");
const OVERLAYS = resolve(ROOT, "overlays");
const storyboard = JSON.parse(readFileSync("e2e/launch-media/storyboard.json", "utf-8"));
const HOLD = storyboard.hold;
const FADE = 0.35;

const dirs = ["scenes", "landing", "video", "work"].map((name) => resolve(ROOT, name));
dirs.forEach((dir) => mkdirSync(dir, { recursive: true }));
const [SCENES, LANDING, VIDEO, WORK] = dirs;

function ffmpeg(args) {
  execFileSync("ffmpeg", ["-hide_banner", "-loglevel", "error", "-y", ...args], { stdio: "inherit" });
}

const X264 = ["-c:v", "libx264", "-preset", "slow", "-pix_fmt", "yuv420p", "-movflags", "+faststart"];

/** Fotogrammi a tempo variabile -> 30 fps costanti, 1920x1080. */
function rawClip(id) {
  const meta = JSON.parse(readFileSync(resolve(RAW, id, "scene.json"), "utf-8"));
  const lines = [];
  meta.frames.forEach((frame, index) => {
    const next = meta.frames[index + 1]?.t ?? meta.end;
    lines.push(`file '${resolve(RAW, id, frame.file)}'`, `duration ${Math.max(0.034, next - frame.t).toFixed(4)}`);
  });
  lines.push(`file '${resolve(RAW, id, meta.frames.at(-1).file)}'`);
  const list = resolve(WORK, `${id}.txt`);
  writeFileSync(list, lines.join("\n"));
  const out = resolve(WORK, `${id}.mp4`);
  ffmpeg(["-f", "concat", "-safe", "0", "-i", list, "-vf", "fps=30,scale=1920:1080:flags=lanczos,format=yuv420p", ...X264, "-crf", "14", out]);
  return { file: out, duration: meta.end, marks: meta.marks };
}

function captionFilter(index, start, end) {
  return `[${index}:v]format=rgba,fade=t=in:st=${start}:d=${FADE}:alpha=1,fade=t=out:st=${(end - FADE).toFixed(2)}:d=${FADE}:alpha=1[c${index}]`;
}

/** La scena del video: testi nel tempo di attesa, disclaimer, dissolvenze ai bordi. */
function sceneClip(scene, raw) {
  const inputs = ["-i", raw.file];
  const filters = [];
  let last = "0:v";
  let n = 1;
  const overlay = (png, start, end) => {
    inputs.push("-loop", "1", "-t", String(raw.duration), "-i", png);
    filters.push(captionFilter(n, start, end));
    filters.push(`[${last}][c${n}]overlay=0:0:enable='between(t,${start},${end})'[v${n}]`);
    last = `v${n}`;
    n++;
  };
  if (scene.caption) overlay(resolve(OVERLAYS, `${scene.id}.png`), 0.25, HOLD - 0.2);
  (scene.captions ?? []).forEach((extra, index) => {
    const at = raw.marks[extra.mark] ?? HOLD;
    overlay(resolve(OVERLAYS, `${scene.id}-${index + 1}.png`), at + 0.3, Math.min(raw.duration - 0.1, at + 0.3 + extra.duration));
  });
  if (!scene.card) {
    inputs.push("-loop", "1", "-t", String(raw.duration), "-i", resolve(OVERLAYS, "disclaimer.png"));
    filters.push(`[${last}][${n}:v]overlay=0:0[v${n}]`);
    last = `v${n}`;
  }
  const end = (raw.duration - 0.3).toFixed(2);
  filters.push(`[${last}]fade=t=in:st=0:d=0.3:color=white,fade=t=out:st=${end}:d=0.3:color=white,format=yuv420p[out]`);
  const out = resolve(SCENES, `${scene.id}.mp4`);
  ffmpeg([...inputs, "-filter_complex", filters.join(";"), "-map", "[out]", "-t", String(raw.duration), ...X264, "-crf", "18", "-r", "30", out]);
  return out;
}

/** Clip per la landing: l'azione senza testo, con il disclaimer. MP4 + WebM + poster. */
function landingClip(name, raw, from, duration) {
  const base = resolve(LANDING, name);
  const filter = `[0:v][1:v]overlay=0:0,format=yuv420p[out]`;
  const args = ["-ss", String(from), "-t", String(duration), "-i", raw, "-loop", "1", "-t", String(duration), "-i", resolve(OVERLAYS, "disclaimer.png"), "-filter_complex", filter, "-map", "[out]", "-an"];
  ffmpeg([...args, ...X264, "-crf", "21", `${base}.mp4`]);
  ffmpeg([...args, "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "34", "-row-mt", "1", "-deadline", "good", `${base}.webm`]);
  ffmpeg(["-ss", "0.5", "-i", `${base}.mp4`, "-frames:v", "1", "-q:v", "3", `${base}.jpg`]);
}

const raws = {};
const sceneFiles = [];
for (const scene of storyboard.scenes) {
  if (!existsSync(resolve(RAW, scene.id, "scene.json"))) {
    console.warn(`manca la registrazione di ${scene.id}: saltata`);
    continue;
  }
  const raw = rawClip(scene.id);
  raws[scene.id] = raw;
  sceneFiles.push(sceneClip(scene, raw));
  if (scene.landing) landingClip(scene.landing, raw.file, HOLD, Math.max(2, raw.duration - HOLD - 0.3));
  console.log(`scena ${scene.id}: ${raw.duration.toFixed(1)} s`);
}

const heroParts = storyboard.hero.filter((part) => raws[part.scene]);
if (heroParts.length) {
  const parts = heroParts.map((part, index) => {
    const out = resolve(WORK, `hero-${index}.mp4`);
    ffmpeg(["-ss", String(part.from), "-t", String(part.duration), "-i", raws[part.scene].file, "-vf", `fade=t=in:st=0:d=0.4:color=white,fade=t=out:st=${part.duration - 0.4}:d=0.4:color=white`, ...X264, "-crf", "14", out]);
    return out;
  });
  const list = resolve(WORK, "hero.txt");
  writeFileSync(list, parts.map((file) => `file '${file}'`).join("\n"));
  const hero = resolve(WORK, "hero.mp4");
  ffmpeg(["-f", "concat", "-safe", "0", "-i", list, "-c", "copy", hero]);
  landingClip("hero-loop", hero, 0, heroParts.reduce((sum, part) => sum + part.duration, 0));
}

if (sceneFiles.length) {
  const list = resolve(WORK, "video.txt");
  writeFileSync(list, sceneFiles.map((file) => `file '${file}'`).join("\n"));
  const video = resolve(VIDEO, "delir-presentazione-it.mp4");
  ffmpeg(["-f", "concat", "-safe", "0", "-i", list, "-c", "copy", "-movflags", "+faststart", video]);
  const seconds = execFileSync("ffprobe", ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video]).toString().trim();
  console.log(`video completo: ${video} (${Number(seconds).toFixed(1)} s)`);
}
