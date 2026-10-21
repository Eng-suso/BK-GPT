"""Montaggio dei video della landing, fotogramma per fotogramma.

Legge le scene registrate da `e2e/launch-media/landing-videos.spec.ts`
(`artifacts/landing-videos/raw/<scena>/`), le targhette e i tagli di
`e2e/launch-media/landing-videos.json`, e monta per ogni taglio un video
1920x1080 a 30 fps:

- il prodotto sempre intero, dentro una cornice, a velocita' reale (mai
  accelerato);
- sotto, fuori dal prodotto, la targhetta IT/EN di cio' che accade, il capitolo
  e il disclaimer: nessun testo copre l'interfaccia;
- camera ferma; l'unico zoom e' quello registrato in cattura (`rec.focus`),
  leggero, mentre si scrive;
- dissolvenze fra le parti e fra le targhette.

    python3 scripts/landing_videos_edit.py                 # tutti i tagli
    python3 scripts/landing_videos_edit.py 05-simulation   # solo quello

Esce in `artifacts/landing-videos/video/<taglio>.mp4` (master) e
`artifacts/landing-videos/web/` (MP4 + WebM + poster + sottotitoli IT/EN
per la landing).
"""

from __future__ import annotations

import bisect
import json
import math
import subprocess
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path("artifacts/landing-videos")
RAW = ROOT / "raw"
OVERLAYS = ROOT / "overlays"
VIDEO = ROOT / "video"
WEB = ROOT / "web"
SCRIPT = json.loads(Path("e2e/launch-media/landing-videos.json").read_text(encoding="utf-8"))

W, H, FPS = 1920, 1080, 30
BACKGROUND = (237, 242, 248)
# Il prodotto: 86% del fotogramma, in alto; sotto resta la fascia dei testi.
SCALE = 0.86
PW, PH = round(W * SCALE), round(H * SCALE)
PX, PY = (W - PW) // 2, 22
STRIP = (PY + PH + H) // 2  # centro verticale della fascia dei testi
RADIUS = 16
CROSSFADE = 0.6  # secondi fra due parti
TAG_IN, TAG_OUT = 0.5, 0.35
CAMERA_MOVE = 1.2
EDGE = 0.5  # apertura e chiusura dallo sfondo


def ease_in_out(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return 4 * x**3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def ease_out(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3


@lru_cache(maxsize=8)
def load_frame(path: str) -> Image.Image:
    image = Image.open(path).convert("RGB")
    return image if image.size == (W, H) else image.resize((W, H), Image.LANCZOS)


@lru_cache(maxsize=None)
def overlay(name: str) -> Image.Image | None:
    path = OVERLAYS / f"{name}.png"
    return Image.open(path).convert("RGBA") if path.exists() else None


def base_canvas() -> tuple[Image.Image, Image.Image]:
    """Lo sfondo con l'ombra della cornice, e la maschera ad angoli arrotondati."""
    canvas = Image.new("RGB", (W, H), BACKGROUND)
    shadow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(shadow).rounded_rectangle((PX, PY + 10, PX + PW, PY + PH + 10), RADIUS, fill=70)
    shadow = shadow.filter(ImageFilter.GaussianBlur(22))
    canvas.paste(Image.new("RGB", (W, H), (148, 163, 184)), (0, 0), shadow)
    border = ImageDraw.Draw(canvas)
    border.rounded_rectangle((PX - 1, PY - 1, PX + PW, PY + PH), RADIUS + 1, outline=(214, 223, 235), width=1)
    mask = Image.new("L", (PW, PH), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, PW - 1, PH - 1), RADIUS, fill=255)
    return canvas, mask


BASE, MASK = base_canvas()


def draw(canvas: Image.Image, image: Image.Image | None, x: int, y: int, alpha: float) -> None:
    if image is None or alpha <= 0.003:
        return
    if alpha < 0.997:
        image = image.copy()
        image.putalpha(image.getchannel("A").point(lambda v: int(v * alpha)))
    canvas.paste(image, (x, y), image)


@dataclass
class Part:
    """Un tratto di una scena registrata dentro un taglio."""

    scene: str
    chapter: str
    raw0: float
    raw1: float
    frames_t: list[float]
    frames_file: list[str]
    tags: list[tuple[float, str]]  # (tempo del tratto, nome della targhetta)
    camera: list[tuple[float, float, float, float]] = field(default_factory=list)  # (t, cx, cy, log zoom)

    @property
    def duration(self) -> float:
        return self.raw1 - self.raw0

    def product(self, t: float) -> Image.Image:
        raw = self.raw0 + t
        image = load_frame(self.frames_file[max(0, bisect.bisect_right(self.frames_t, raw) - 1)])
        cx, cy, logz = W / 2, H / 2, 0.0
        previous = (cx, cy, logz)
        for t_k, kx, ky, kz in self.camera:
            p = ease_in_out((t - t_k) / CAMERA_MOVE)
            if p <= 0:
                break
            cx += (kx - previous[0]) * p
            cy += (ky - previous[1]) * p
            logz += (kz - previous[2]) * p
            previous = (kx, ky, kz)
        zoom = math.exp(logz)
        box = (0, 0, W, H)
        if zoom > 1.002:
            cw, ch = W / zoom, H / zoom
            x0 = min(max(cx - cw / 2, 0), W - cw)
            y0 = min(max(cy - ch / 2, 0), H - ch)
            box = (x0, y0, x0 + cw, y0 + ch)
        return image.resize((PW, PH), Image.LANCZOS if zoom > 1.002 else Image.BILINEAR, box=box, reducing_gap=2.0)

    def tag_at(self, t: float) -> tuple[str, float, float] | None:
        """La targhetta attiva, con l'inizio e la fine del suo intervallo nel tratto."""
        if not self.tags:
            return None
        index = max(0, bisect.bisect_right([at for at, _ in self.tags], t) - 1)
        start = self.tags[index][0] if index > 0 else 0.0
        end = self.tags[index + 1][0] if index + 1 < len(self.tags) else self.duration
        return self.tags[index][1], start, end


def build_part(entry: dict, cut: dict) -> Part:
    scene = entry["scene"]
    meta = json.loads((RAW / scene / "scene.json").read_text(encoding="utf-8"))
    offset = meta.get("offset", 0.0)
    marks = {name: value - offset for name, value in meta.get("marks", {}).items()}
    mark = lambda value, default: default if value is None else value if isinstance(value, (int, float)) else marks[value]
    raw0 = mark(entry.get("from"), 0.0)
    raw1 = min(mark(entry.get("to"), marks.get("end", meta["end"])), meta["end"] - 0.05)
    frames_t = [frame["t"] for frame in meta["frames"]]
    frames_file = [str(RAW / scene / frame["file"]) for frame in meta["frames"]]
    tags = sorted((at - raw0, name[4:]) for name, at in marks.items() if name.startswith("tag:"))
    # La targhetta in corso all'inizio del tratto vale da subito.
    before = [item for item in tags if item[0] <= 0.05]
    tags = ([(0.0, before[-1][1])] if before else []) + [item for item in tags if 0.05 < item[0] < raw1 - raw0 - 1.0]
    part = Part(scene, entry.get("chapter", cut["chapter"]), raw0, raw1, frames_t, frames_file, tags)
    viewport = meta.get("viewport") or {"width": W, "height": H}
    scale = W / viewport["width"]
    for key in meta.get("camera", []):
        t = key["t"] - offset - raw0
        if t < -CAMERA_MOVE or t >= part.duration - 0.2:
            continue
        rect = key.get("rect")
        if not rect:
            part.camera.append((max(0.0, t), W / 2, H / 2, 0.0))
            continue
        rw, rh = rect["width"] * scale, rect["height"] * scale
        zoom = max(1.0, min(key.get("zoom", 1.3), W / rw, H / rh))
        part.camera.append((max(0.0, t), (rect["x"] + rect["width"] / 2) * scale, (rect["y"] + rect["height"] / 2) * scale, math.log(zoom)))
    return part


def chrome(canvas: Image.Image, part: Part, t: float, weight: float) -> None:
    """Targhetta, capitolo e disclaimer della parte, nella fascia sotto il prodotto."""
    chapter = overlay(f"chapter-{part.chapter}")
    if chapter:
        draw(canvas, chapter, PX, STRIP - chapter.height // 2, weight)
    active = part.tag_at(t)
    if not active:
        return
    name, start, end = active
    image = overlay(f"tag-{part.scene}-{name}")
    if image is None:
        print(f"  manca la targhetta {part.scene}:{name}")
        return
    rise = ease_out((t - start) / TAG_IN) if start > 0 else 1.0
    fall = min(1.0, (end - t) / TAG_OUT) if end < part.duration - 0.01 else 1.0
    alpha = max(0.0, min(rise, fall)) * weight
    draw(canvas, image, (W - image.width) // 2, STRIP - image.height // 2 + round((1 - rise) * 14), alpha)


def frame_of(part: Part, t: float, weight: float = 1.0) -> Image.Image:
    canvas = BASE.copy()
    canvas.paste(part.product(t), (PX, PY), MASK)
    chrome(canvas, part, t, weight)
    return canvas


def render(name: str, cut: dict) -> Path:
    parts = [build_part(entry, cut) for entry in cut["parts"]]
    starts, at = [], 0.0
    for part in parts:
        starts.append(at)
        at += part.duration - CROSSFADE
    total = at + CROSSFADE
    disclaimer = overlay("disclaimer")
    VIDEO.mkdir(parents=True, exist_ok=True)
    out = VIDEO / f"{name}.mp4"
    encoder = subprocess.Popen(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
         "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)],
        stdin=subprocess.PIPE,
    )
    cues: list[tuple[float, float, str, str]] = []  # (inizio, fine, scena, targhetta) nel taglio
    for index, part in enumerate(parts):
        for k, (tag_at, tag) in enumerate(part.tags):
            end = part.tags[k + 1][0] if k + 1 < len(part.tags) else part.duration
            cues.append((starts[index] + tag_at, starts[index] + end, part.scene, tag))
    frames = int(round(total * FPS))
    for n in range(frames):
        t = n / FPS
        active = [i for i in range(len(parts)) if starts[i] <= t < starts[i] + parts[i].duration] or [len(parts) - 1]
        if len(active) == 1:
            i = active[0]
            canvas = frame_of(parts[i], min(t - starts[i], parts[i].duration - 0.001))
        else:
            a, b = active[0], active[1]
            mix = ease_in_out((t - starts[b]) / CROSSFADE)
            canvas = Image.blend(frame_of(parts[a], t - starts[a], 1 - mix), frame_of(parts[b], t - starts[b], mix), mix)
        if disclaimer:
            draw(canvas, disclaimer, PX + PW - disclaimer.width, STRIP - disclaimer.height // 2, 1.0)
        edge = min(1.0, t / EDGE, (total - t) / EDGE)
        if edge < 1:
            canvas = Image.blend(Image.new("RGB", (W, H), BACKGROUND), canvas, max(0.0, edge))
        encoder.stdin.write(canvas.tobytes())
        if n % (FPS * 10) == 0:
            print(f"  {name}: {t:5.1f}/{total:.1f} s", flush=True)
    encoder.stdin.close()
    encoder.wait()
    print(f"taglio {name}: {out} ({total:.1f} s)")
    captions(name, cues)
    web_export(name, out, poster=min(total - 1, cut.get("poster", 4.0)))
    return out


def vtt_time(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    return f"{ms // 3_600_000:02d}:{ms // 60_000 % 60:02d}:{ms // 1000 % 60:02d}.{ms % 1000:03d}"


def captions(name: str, cues: list[tuple[float, float, str, str]]) -> None:
    """Sottotitoli IT e EN dalle targhette: sul telefono il testo si legge qui."""
    WEB.mkdir(parents=True, exist_ok=True)
    for language in ("it", "en"):
        lines = ["WEBVTT", ""]
        for start, end, scene, tag in cues:
            text = SCRIPT["scenes"][scene][tag][language]
            lines += [f"{vtt_time(start)} --> {vtt_time(max(start + 0.5, end - 0.05))}", text, ""]
        (WEB / f"{name}.{language}.vtt").write_text("\n".join(lines), encoding="utf-8")


def web_export(name: str, master: Path, poster: float) -> None:
    """MP4 H.264 e WebM VP9 per la landing, piu' il poster."""
    base = WEB / name
    run = lambda *args: subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)
    run("-i", str(master), "-an", "-c:v", "libx264", "-profile:v", "high", "-preset", "slow", "-crf", "27", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", f"{base}.mp4")
    run("-i", str(master), "-an", "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "38", "-row-mt", "1", "-deadline", "good", "-cpu-used", "3",
        "-pix_fmt", "yuv420p", f"{base}.webm")
    run("-ss", str(poster), "-i", str(master), "-frames:v", "1", "-q:v", "3", f"{base}.jpg")
    for ext in ("mp4", "webm", "jpg"):
        print(f"  {base}.{ext}: {Path(f'{base}.{ext}').stat().st_size / 1024:.0f} KB")


def main() -> None:
    only = set(sys.argv[1:])
    for name, cut in SCRIPT["cuts"].items():
        if not only or name in only:
            render(name, cut)


if __name__ == "__main__":
    main()
