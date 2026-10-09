#!/usr/bin/env node
/**
 * Montaggio dei media di lancio con ffmpeg, dai fotogrammi registrati da
 * `e2e/launch-media/capture.spec.ts`.
 *
 * Esce in artifacts/launch-media/:
 *   scenes/<id>.mp4          scena del video, con testo a schermo e disclaimer
 *   landing/<nome>.mp4|webm  clip in loop per la landing (senza testo) + poster
 *   landing/hero-loop.*      il loop dell'hero (storyboard.json -> hero)
 *   video/delir-presentazione-it.mp4   tutte le scene per intero (materiale di montaggio)
 *   video/delir-<taglio>-it.mp4        i tagli di storyboard.json -> cuts (90s, 150s)
 *
 *   node scripts/launch_media_render.mjs               # tutte le scene
 *   node scripts/launch_media_render.mjs 01-gancio     # solo quelle, riusando le altre
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

const X264 = ["-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p", "-movflags", "+faststart"];

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

function loadRaw(id) {
  const meta = JSON.parse(readFileSync(resolve(RAW, id, "scene.json"), "utf-8"));
  return { file: resolve(WORK, `${id}.mp4`), duration: meta.end, marks: meta.marks };
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
  ffmpeg([...args, "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "34", "-row-mt", "1", "-deadline", "good", "-cpu-used", "4", `${base}.webm`]);
  ffmpeg(["-ss", "0.5", "-i", `${base}.mp4`, "-frames:v", "1", "-q:v", "3", `${base}.jpg`]);
}

const only = new Set(process.argv.slice(2));
const raws = {};
const sceneFiles = [];
for (const scene of storyboard.scenes) {
  const done = resolve(SCENES, `${scene.id}.mp4`);
  if (only.size && !only.has(scene.id)) {
    if (existsSync(done)) sceneFiles.push(done);
    if (existsSync(resolve(WORK, `${scene.id}.mp4`))) raws[scene.id] = loadRaw(scene.id);
    continue;
  }
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
if (heroParts.length && heroParts.length === storyboard.hero.length) {
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

/**
 * Un taglio: per ogni scena, `hold` secondi fermi con il testo (gli ultimi
 * dell'attesa registrata), poi `keep` secondi d'azione accelerati di `speed`.
 * Le card si accelerano per intero.
 */
function cutScene(cutName, cut, entry) {
  const scene = storyboard.scenes.find((item) => item.id === entry.id);
  const raw = raws[entry.id];
  const speed = entry.speed ?? 1;
  const inputs = ["-i", raw.file];
  const filters = [];
  let total;
  if (scene.card) {
    total = raw.duration / speed;
    filters.push(`[0:v]setpts=(PTS-STARTPTS)/${speed},fps=30[base]`);
  } else {
    const hold = Math.min(cut.hold, HOLD);
    const keep = Math.min(entry.keep ?? Infinity, raw.duration - HOLD - 0.3);
    total = hold + keep / speed;
    filters.push(
      `[0:v]trim=start=${HOLD - hold}:end=${HOLD},setpts=PTS-STARTPTS[a]`,
      `[0:v]trim=start=${HOLD}:end=${HOLD + keep},setpts=(PTS-STARTPTS)/${speed}[b]`,
      `[a][b]concat=n=2:v=1,fps=30[base]`,
    );
  }
  let last = "base";
  let n = 1;
  const overlay = (png, start, end) => {
    if (start >= total - 0.3) return;
    end = Math.min(end, total - 0.1);
    inputs.push("-loop", "1", "-t", total.toFixed(3), "-i", png);
    filters.push(captionFilter(n, start.toFixed(2), end));
    filters.push(`[${last}][c${n}]overlay=0:0:enable='between(t,${start.toFixed(2)},${end.toFixed(2)})'[v${n}]`);
    last = `v${n}`;
    n++;
  };
  if (scene.caption && !scene.card) overlay(resolve(OVERLAYS, `${scene.id}.png`), 0.15, Math.min(cut.hold, HOLD) - 0.15);
  (scene.captions ?? []).forEach((extra, index) => {
    const at = Math.min(cut.hold, HOLD) + ((raw.marks[extra.mark] ?? HOLD) - HOLD) / speed;
    overlay(resolve(OVERLAYS, `${scene.id}-${index + 1}.png`), at + 0.2, at + 0.2 + extra.duration / Math.max(1, speed * 0.85));
  });
  if (!scene.card) {
    inputs.push("-loop", "1", "-t", total.toFixed(3), "-i", resolve(OVERLAYS, "disclaimer.png"));
    filters.push(`[${last}][${n}:v]overlay=0:0[v${n}]`);
    last = `v${n}`;
  }
  const end = (total - 0.25).toFixed(2);
  filters.push(`[${last}]fade=t=in:st=0:d=0.25:color=white,fade=t=out:st=${end}:d=0.25:color=white,format=yuv420p[out]`);
  const out = resolve(WORK, `cut-${cutName}-${entry.id}.mp4`);
  ffmpeg([...inputs, "-filter_complex", filters.join(";"), "-map", "[out]", "-t", total.toFixed(3), ...X264, "-crf", "18", "-r", "30", out]);
  return out;
}

for (const [cutName, cut] of Object.entries(storyboard.cuts ?? {})) {
  const missing = cut.scenes.filter((entry) => !raws[entry.id]).map((entry) => entry.id);
  if (missing.length) {
    console.warn(`taglio ${cutName}: mancano ${missing.join(", ")}`);
    continue;
  }
  const parts = cut.scenes.map((entry) => cutScene(cutName, cut, entry));
  const list = resolve(WORK, `cut-${cutName}.txt`);
  writeFileSync(list, parts.map((file) => `file '${file}'`).join("\n"));
  const video = resolve(VIDEO, `delir-${cutName}-it.mp4`);
  ffmpeg(["-f", "concat", "-safe", "0", "-i", list, "-c", "copy", "-movflags", "+faststart", video]);
  const seconds = execFileSync("ffprobe", ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video]).toString().trim();
  console.log(`taglio ${cutName}: ${video} (${Number(seconds).toFixed(1)} s)`);
}
