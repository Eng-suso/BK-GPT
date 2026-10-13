"""Montaggio dei video del piano prodotto (16:9 e 4:5), sempre a velocita' 1x.

Legge le riprese di Playwright (`artifacts/launch-media/raw/<scena>/`, scritte
da `e2e/launch-media/recorder.ts`) e i tagli di `e2e/launch-media/montage.json`.
Per ogni taglio e ogni formato:

- la camera segue le inquadrature registrate (`rec.focus` / `rec.wide`): nel
  4:5 usa l'area `narrow` quando la scena ne indica una, altrimenti la stessa;
- il logo bpmn.io (zone `forbidden` della ripresa) non entra mai in quadro: la
  finestra si sposta o si stringe finche' non lo esclude;
- il testo piu' piccolo inquadrato (`minFont`) deve restare almeno 11 px alla
  dimensione mostrata sul sito (`display` del formato): sotto, lo script si ferma;
- fra due scene taglio netto o dissolvenza di 0,3 s; nessuna accelerazione.

Ogni taglio esce in ogni lingua del sito (italiano e inglese), in
`artifacts/launch-media/video/`: mp4 H.264 + webm VP9 senza audio, 30 fps, e il
poster jpg/webp. Nomi come i VTT del sito: `hero-loop.mp4` (it),
`hero-loop.en.mp4`, `hero-loop-4x5.mp4`, `hero-loop-4x5.en.mp4`.

    python3 scripts/launch_media_montage.py hero        # tutte le lingue
    python3 scripts/launch_media_montage.py hero it     # solo italiano
"""

from __future__ import annotations

import bisect
import json
import math
import subprocess
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path("artifacts/launch-media")
RAW = ROOT / "raw"
OVERLAYS = ROOT / "overlays"
VIDEO = ROOT / "video"
CONFIG = json.loads(Path("e2e/launch-media/montage.json").read_text(encoding="utf-8"))
FPS = CONFIG.get("fps", 30)
CAMERA_MOVE = 0.9  # secondi di un movimento di camera
MIN_TEXT_PX = 11  # testo UI minimo alla dimensione mostrata
MAX_OVERVIEW = 2.0  # secondi di inquadratura larga, solo per orientarsi


def ease_in_out(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return 4 * x**3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


@dataclass(frozen=True)
class Box:
    x: float
    y: float
    w: float
    h: float

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2

    def hits(self, other: "Box") -> bool:
        return self.x < other.x + other.w and other.x < self.x + self.w and self.y < other.y + other.h and other.y < self.y + self.h


def window_for(target: Box | None, aspect: float, vw: float, vh: float, zoom: float, forbidden: list[Box]) -> Box:
    """La finestra con le proporzioni del formato che contiene `target`."""
    if target is None:
        w, h = (vw, vw / aspect) if vw / vh < aspect else (vh * aspect, vh)
        cx, cy = vw / 2, vh / 2
    else:
        w = max(target.w, target.h * aspect, vw / zoom if aspect >= 1 else vh * aspect / zoom)
        h = w / aspect
        cx, cy = target.cx, target.cy
    if w > vw:
        w, h = vw, vw / aspect
    if h > vh:
        w, h = vh * aspect, vh

    def place(cx: float, cy: float, w: float, h: float) -> Box:
        return Box(min(max(cx - w / 2, 0), vw - w), min(max(cy - h / 2, 0), vh - h), w, h)

    box = place(cx, cy, w, h)
    for _ in range(60):
        blockers = [zone for zone in forbidden if box.hits(zone)]
        if not blockers:
            return box
        zone = blockers[0]
        # Prima si sposta (su o a sinistra: il logo sta in basso), poi si stringe.
        moves = [
            Box(box.x, zone.y - box.h, box.w, box.h),
            Box(zone.x - box.w, box.y, box.w, box.h),
            Box(box.x, zone.y + zone.h, box.w, box.h),
            Box(zone.x + zone.w, box.y, box.w, box.h),
        ]
        valid = [m for m in moves if m.x >= 0 and m.y >= 0 and m.x + m.w <= vw and m.y + m.h <= vh and not any(m.hits(z) for z in forbidden)]
        if valid:
            return min(valid, key=lambda m: abs(m.x - box.x) + abs(m.y - box.y))
        box = place(box.cx, box.cy, box.w * 0.95, box.h * 0.95)
    raise SystemExit("! nessuna inquadratura esclude il logo bpmn.io")


@lru_cache(maxsize=8)
def load_frame(path: str) -> Image.Image:
    return Image.open(path).convert("RGB")


class Shot:
    """Una scena registrata, nel tratto [from, from + duration], in un formato."""

    def __init__(self, entry: dict, fmt: dict, name: str):
        self.id = entry["scene"]
        meta = json.loads((RAW / self.id / "scene.json").read_text(encoding="utf-8"))
        self.offset = meta.get("offset", 0.0)
        self.start = entry.get("from", 0.0)
        self.duration = entry.get("duration", meta["end"] - self.start - 0.1)
        self.frames_t = [f["t"] for f in meta["frames"]]
        self.frames_file = [str(RAW / self.id / f["file"]) for f in meta["frames"]]
        viewport = meta["viewport"]
        self.vw, self.vh = viewport["width"], viewport["height"]
        self.out_w, self.out_h = fmt["size"]
        aspect = self.out_w / self.out_h
        portrait = aspect < 1
        forbidden = [Box(z["x"] - 6, z["y"] - 6, z["width"] + 12, z["height"] + 12) for z in meta.get("forbidden", [])]
        self.camera: list[tuple[float, Box]] = []
        self.problems: list[str] = []
        for key in meta.get("camera", []):
            rect = key.get("narrow") if portrait and key.get("narrow") else key.get("rect")
            target = Box(rect["x"], rect["y"], rect["width"], rect["height"]) if rect else None
            # La fascia in basso resta alla dicitura "caso dimostrativo": l'area da
            # mostrare sta sopra.
            if target and fmt.get("reserve"):
                target = Box(target.x, target.y, target.w, target.h / (1 - fmt["reserve"]))
            window = window_for(target, aspect, self.vw, self.vh, key.get("zoom", 1.6), forbidden)
            t = key["t"] - self.offset - self.start
            self.camera.append((t, window))
            font = key.get("minFont")
            if font and t < self.duration:
                shown = font * fmt["display"] / window.w
                if shown < MIN_TEXT_PX:
                    self.problems.append(f"{name}/{self.id} a {max(t, 0):.1f} s: testo {font:.1f} px mostrato a {shown:.1f} px (minimo {MIN_TEXT_PX})")
        # Colpo d'insieme (o campo largo): al massimo 2 s, poi la camera stringe.
        keys = meta.get("camera", [])
        for index, key in enumerate(keys):
            if key.get("overview") or not key.get("rect"):
                start = key["t"] - self.offset - self.start
                end = keys[index + 1]["t"] - self.offset - self.start if index + 1 < len(keys) else self.duration
                if min(end, self.duration) - max(start, 0) > MAX_OVERVIEW + CAMERA_MOVE:
                    self.problems.append(f"{name}/{self.id} a {max(start, 0):.1f} s: inquadratura larga per {min(end, self.duration) - max(start, 0):.1f} s (massimo {MAX_OVERVIEW})")
        if not self.camera or self.camera[0][0] > 0:
            self.camera.insert(0, (-1.0, window_for(None, aspect, self.vw, self.vh, 1.0, forbidden)))

    def window(self, t: float) -> Box:
        current = self.camera[0][1]
        for t_k, box in self.camera[1:]:
            p = ease_in_out((t - t_k) / CAMERA_MOVE)
            if p <= 0:
                break
            # Il centro si muove in lineare, la larghezza in scala logaritmica.
            w = math.exp(math.log(current.w) + (math.log(box.w) - math.log(current.w)) * p)
            cx = current.cx + (box.cx - current.cx) * p
            cy = current.cy + (box.cy - current.cy) * p
            h = w * box.h / box.w
            # A meta' movimento la finestra resta dentro lo schermo.
            current = Box(min(max(cx - w / 2, 0), self.vw - w), min(max(cy - h / 2, 0), self.vh - h), w, h)
        return current

    def frame(self, t: float) -> np.ndarray:
        raw = self.start + t + self.offset
        index = max(0, bisect.bisect_right(self.frames_t, raw) - 1)
        image = load_frame(self.frames_file[index])
        scale = image.width / self.vw
        box = self.window(t)
        # Arrotondamenti: la finestra non esce mai dal fotogramma.
        crop = (max(0.0, box.x * scale), max(0.0, box.y * scale),
                min(image.width, (box.x + box.w) * scale), min(image.height, (box.y + box.h) * scale))
        out = image.resize((self.out_w, self.out_h), Image.LANCZOS, box=crop)
        return np.asarray(out, dtype=np.float32) / 255.0


def overlay(name: str, size: tuple[int, int]) -> tuple[np.ndarray, np.ndarray] | None:
    path = OVERLAYS / f"{name}.png"
    if not path.exists():
        return None
    image = Image.open(path).convert("RGBA")
    if image.size != size:
        image = image.resize(size, Image.LANCZOS)
    rgba = np.asarray(image, dtype=np.float32) / 255.0
    return rgba[..., :3], rgba[..., 3:4]


def render(name: str, cut: dict, fmt_name: str, lang: str) -> list[str]:
    fmt = CONFIG["formats"][fmt_name] | cut.get("formats", {}).get(fmt_name, {})
    size = tuple(fmt["size"])
    # `{lang}` nei nomi: ogni lingua ha la sua ripresa (interfaccia e caso tradotti).
    localize = lambda text: text.replace("{lang}", lang)
    # Una scena puo' avere la sua ripresa per il formato (`<scena>-4x5`, dal
    # telefono): vince sul ritaglio del desktop.
    def take(scene: str) -> str:
        own = f"{scene}-{fmt_name}"
        return own if (RAW / own / "scene.json").exists() else scene

    shots = [Shot(entry | {"scene": take(localize(entry["scene"]))}, fmt, f"{name}-{lang}-{fmt_name}") for entry in cut["shots"]]
    problems = [p for shot in shots for p in shot.problems]
    if problems:
        return problems
    fade = cut.get("dissolve", 0.0)
    starts, at = [], 0.0
    for shot in shots:
        starts.append(at)
        at += shot.duration
    total = at
    layers = [o for o in (overlay(f"{localize(n)}-{fmt_name}", size) for n in cut.get("overlays", [])) if o]
    first = shots[0].frame(0.0)

    VIDEO.mkdir(parents=True, exist_ok=True)
    # Il sito usa `<id>.<lingua>` (come i VTT): l'italiano resta col nome di oggi.
    base = VIDEO / (cut["files"][fmt_name] + ("" if lang == "it" else f".{lang}"))
    master = base.with_suffix(".master.mp4")
    encoder = subprocess.Popen(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{size[0]}x{size[1]}",
         "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p", str(master)],
        stdin=subprocess.PIPE,
    )
    for n in range(int(round(total * FPS))):
        t = n / FPS
        index = max(0, bisect.bisect_right(starts, t) - 1)
        canvas = shots[index].frame(t - starts[index])
        # Dissolvenza breve verso la scena dopo (o, nel loop, verso l'inizio).
        until_next = starts[index] + shots[index].duration - t
        if fade and until_next < fade:
            following = shots[index + 1].frame(0.0) if index + 1 < len(shots) else first if cut.get("loop") else None
            if following is not None:
                mix = ease_in_out(1 - until_next / fade)
                canvas = canvas * (1 - mix) + following * mix
        for rgb, alpha in layers:
            canvas = canvas * (1 - alpha) + rgb * alpha
        encoder.stdin.write((np.clip(canvas, 0, 1) * 255 + 0.5).astype(np.uint8).tobytes())
    encoder.stdin.close()
    encoder.wait()
    web_export(master, base, cut.get("poster", 0.0))
    print(f"ok {name} {lang} {fmt_name}: {total:.1f} s, {size[0]}x{size[1]}")
    return []


def web_export(master: Path, base: Path, poster: float) -> None:
    """mp4 H.264 e webm VP9 per il sito, senza audio, e il poster."""
    run = lambda *args: subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)
    run("-i", str(master), "-an", "-c:v", "libx264", "-profile:v", "high", "-preset", "slow", "-crf", "23",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", f"{base}.mp4")
    run("-i", str(master), "-an", "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "33", "-row-mt", "1",
        "-deadline", "good", "-cpu-used", "2", "-pix_fmt", "yuv420p", f"{base}.webm")
    run("-ss", str(poster), "-i", str(master), "-frames:v", "1", "-q:v", "3", f"{base}.jpg")
    run("-ss", str(poster), "-i", str(master), "-frames:v", "1", "-c:v", "libwebp", "-quality", "82", f"{base}.webp")
    for ext in ("mp4", "webm", "jpg", "webp"):
        print(f"  {base.name}.{ext}: {Path(f'{base}.{ext}').stat().st_size / 1024:.0f} KB")


def main() -> int:
    args = set(sys.argv[1:])
    # `it` / `en` fra gli argomenti limitano le lingue.
    langs = args & {"it", "en"}
    only = args - langs
    problems: list[str] = []
    for name, cut in CONFIG["cuts"].items():
        if only and name not in only:
            continue
        for lang in [lang for lang in cut.get("languages", ["it"]) if not langs or lang in langs]:
            for fmt_name in cut["files"]:
                problems += render(name, cut, fmt_name, lang)
    for line in problems:
        print("!", line)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
