"""Montaggio dei tagli del video di lancio, fotogramma per fotogramma.

Legge le scene registrate da `e2e/launch-media/capture.spec.ts`
(`artifacts/launch-media/raw/<scena>/`) e i tagli di `storyboard.json`, e
monta per ogni taglio un video 1920x1080 a 30 fps con:

- la camera: zoom e panoramiche morbide sulle inquadrature registrate in
  cattura (`rec.focus` / `rec.wide`), con easing in-out;
- le velocita' del taglio (attesa con il testo, poi segmenti accelerati);
- dissolvenze incrociate fra le scene;
- i testi che entrano dal basso, l'indicatore del percorso del consulente e il
  disclaimer (PNG generati nel browser: `overlays`).

    python3 scripts/launch_media_edit.py            # tutti i tagli
    python3 scripts/launch_media_edit.py 90s        # solo quello

Esce in `artifacts/launch-media/video/delir-<taglio>-it.mp4`.
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

import numpy as np
from PIL import Image

ROOT = Path("artifacts/launch-media")
RAW = ROOT / "raw"
OVERLAYS = ROOT / "overlays"
VIDEO = ROOT / "video"
STORYBOARD = json.loads(Path("e2e/launch-media/storyboard.json").read_text(encoding="utf-8"))
HOLD = STORYBOARD["hold"]
W, H, FPS = 1920, 1080, 30
CROSSFADE = 0.45  # secondi di sovrapposizione fra due scene
CAMERA_MOVE = 0.9  # durata di un movimento di camera (tempo del video)


def ease_in_out(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return 4 * x**3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def ease_out(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3


@lru_cache(maxsize=6)
def load_frame(path: str) -> Image.Image:
    image = Image.open(path).convert("RGB")
    return image if image.size == (W, H) else image.resize((W, H), Image.LANCZOS)


@dataclass
class Overlay:
    """Un PNG trasparente ritagliato al suo contenuto, per comporlo veloce."""

    image: np.ndarray  # RGBA float32 0..1
    x: int
    y: int

    @classmethod
    def load(cls, path: Path) -> "Overlay | None":
        if not path.exists():
            return None
        full = Image.open(path).convert("RGBA")
        if full.size != (W, H):
            full = full.resize((W, H), Image.LANCZOS)
        box = full.getbbox()
        if not box:
            return None
        return cls(np.asarray(full.crop(box), dtype=np.float32) / 255.0, box[0], box[1])

    def draw(self, canvas: np.ndarray, alpha: float, dy: float = 0.0) -> None:
        if alpha <= 0.003:
            return
        h, w = self.image.shape[:2]
        y = int(round(self.y + dy))
        y0, y1 = max(0, y), min(H, y + h)
        if y1 <= y0:
            return
        src = self.image[y0 - y : y1 - y]
        a = src[..., 3:4] * alpha
        region = canvas[y0:y1, self.x : self.x + w]
        region *= 1 - a
        region += src[..., :3] * a


@dataclass
class Piece:
    out0: float
    out1: float
    raw0: float
    speed: float


@dataclass
class Shot:
    """Una scena dentro un taglio: mappa dei tempi, camera, testi."""

    id: str
    scene: dict
    frames_t: list[float]
    frames_file: list[str]
    pieces: list[Piece]
    camera: list[tuple[float, float, float, float]] = field(default_factory=list)  # (t_out, cx, cy, log z)
    captions: list[tuple[Overlay, float, float]] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return self.pieces[-1].out1

    def raw_at(self, t: float) -> float:
        for piece in self.pieces:
            if t < piece.out1 or piece is self.pieces[-1]:
                return piece.raw0 + (min(t, piece.out1) - piece.out0) * piece.speed
        return 0.0

    def out_at(self, raw: float) -> float:
        for piece in self.pieces:
            raw1 = piece.raw0 + (piece.out1 - piece.out0) * piece.speed
            if raw < raw1:
                return piece.out0 + max(0.0, raw - piece.raw0) / piece.speed
        return self.duration

    def frame(self, t: float) -> np.ndarray:
        raw = self.raw_at(t)
        index = max(0, bisect.bisect_right(self.frames_t, raw) - 1)
        image = load_frame(self.frames_file[index])
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
        if zoom > 1.002:
            cw, ch = W / zoom, H / zoom
            x0 = min(max(cx - cw / 2, 0), W - cw)
            y0 = min(max(cy - ch / 2, 0), H - ch)
            image = image.resize((W, H), Image.BICUBIC, box=(x0, y0, x0 + cw, y0 + ch))
        canvas = np.asarray(image, dtype=np.float32) / 255.0
        canvas = canvas.copy()
        for overlay, start, end in self.captions:
            if start <= t <= end:
                rise = ease_out((t - start) / 0.45)
                fade = min(1.0, (end - t) / 0.3)
                overlay.draw(canvas, min(rise, fade), dy=(1 - rise) * 40)
        return canvas


def build_shot(entry: dict, cut: dict) -> Shot:
    scene = next(item for item in STORYBOARD["scenes"] if item["id"] == entry["id"])
    meta = json.loads((RAW / entry["id"] / "scene.json").read_text(encoding="utf-8"))
    offset = meta.get("offset", 0.0)
    end = meta["end"]
    marks = {name: value - offset for name, value in meta.get("marks", {}).items()}
    frames_t = [frame["t"] for frame in meta["frames"]]
    frames_file = [str(RAW / entry["id"] / frame["file"]) for frame in meta["frames"]]

    if scene.get("card"):
        speed = entry.get("speed", 1.0)
        pieces = [Piece(0.0, end / speed, 0.0, speed)]
        hold = 0.0
    else:
        hold = min(cut["hold"], HOLD)
        stop = end - 0.3
        segments = entry.get("segments") or [{"to": HOLD + entry.get("keep", 1e9), "speed": entry.get("speed", 1.0)}]
        pieces = [Piece(0.0, hold, HOLD - hold, 1.0)]
        out, raw = hold, HOLD
        for segment in segments:
            to = segment["to"]
            to = stop if to == "end" else to if isinstance(to, (int, float)) else marks[to]
            to = min(to, stop)
            if to <= raw:
                continue
            length = (to - raw) / segment["speed"]
            pieces.append(Piece(out, out + length, raw, segment["speed"]))
            out, raw = out + length, to

    shot = Shot(entry["id"], scene, frames_t, frames_file, pieces)

    # Camera: dal rettangolo registrato (px CSS) allo zoom sul fotogramma.
    viewport = meta.get("viewport") or {"width": W, "height": H}
    scale = W / viewport["width"]
    for key in meta.get("camera", []):
        t_out = shot.out_at(key["t"] - offset)
        if t_out >= shot.duration - 0.2:
            continue
        rect = key.get("rect")
        if not rect:
            shot.camera.append((t_out, W / 2, H / 2, 0.0))
            continue
        rw, rh = rect["width"] * scale, rect["height"] * scale
        zoom = max(1.0, min(key.get("zoom", 1.6), W / rw, H / rh))
        cx = (rect["x"] + rect["width"] / 2) * scale
        cy = (rect["y"] + rect["height"] / 2) * scale
        shot.camera.append((t_out, cx, cy, math.log(zoom)))

    if scene.get("caption") and not scene.get("card"):
        overlay = Overlay.load(OVERLAYS / f"{scene['id']}.png")
        if overlay:
            shot.captions.append((overlay, 0.12, hold - 0.05))
    for index, extra in enumerate(scene.get("captions", [])):
        overlay = Overlay.load(OVERLAYS / f"{scene['id']}-{index + 1}.png")
        at = shot.out_at(marks.get(extra["mark"], HOLD)) + 0.2
        if overlay and at < shot.duration - 0.5:
            shot.captions.append((overlay, at, min(shot.duration - 0.1, at + extra["duration"] / max(1.0, entry.get("speed", 1.0) * 0.85))))
    return shot


def render(name: str, cut: dict) -> Path:
    shots = [build_shot(entry, cut) for entry in cut["scenes"]]
    starts, at = [], 0.0
    for shot in shots:
        starts.append(at)
        at += shot.duration - CROSSFADE
    total = at + CROSSFADE
    stages = {i: Overlay.load(OVERLAYS / f"stage-{i}.png") for i in range(len(STORYBOARD["stages"]) + 1)}
    disclaimer = Overlay.load(OVERLAYS / "disclaimer.png")

    VIDEO.mkdir(parents=True, exist_ok=True)
    out = VIDEO / f"delir-{name}-it.mp4"
    encoder = subprocess.Popen(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
         "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)],
        stdin=subprocess.PIPE,
    )
    frames = int(round(total * FPS))
    for n in range(frames):
        t = n / FPS
        active = [(i, t - starts[i]) for i in range(len(shots)) if starts[i] <= t < starts[i] + shots[i].duration]
        if not active:
            active = [(len(shots) - 1, shots[-1].duration - 0.001)]
        layers = []  # (shot index, peso)
        if len(active) == 1:
            layers = [(active[0][0], 1.0)]
            canvas = shots[active[0][0]].frame(active[0][1])
        else:
            (a, ta), (b, tb) = active[0], active[1]
            mix = ease_in_out(tb / CROSSFADE)
            canvas = shots[a].frame(ta) * (1 - mix) + shots[b].frame(tb) * mix
            layers = [(a, 1 - mix), (b, mix)]
        # Percorso e disclaimer: fissi sullo schermo, sopra la camera.
        stage_of = [shots[i].scene.get("stage") for i, _ in layers]
        if len(layers) == 2 and stage_of[0] == stage_of[1]:
            layers, stage_of = [(layers[0][0], 1.0)], [stage_of[0]]
        for (i, weight), stage in zip(layers, stage_of):
            if stage is not None and stages.get(stage):
                stages[stage].draw(canvas, weight)
        product = sum(weight for i, weight in layers if not shots[i].scene.get("card"))
        if disclaimer:
            disclaimer.draw(canvas, min(1.0, product))
        # Apertura e chiusura dal bianco.
        edge = min(1.0, t / 0.4, (total - t) / 0.6)
        if edge < 1:
            canvas = canvas * edge + (1 - edge)
        encoder.stdin.write((np.clip(canvas, 0, 1) * 255 + 0.5).astype(np.uint8).tobytes())
        if n % (FPS * 10) == 0:
            print(f"  {name}: {t:5.1f}/{total:.1f} s", flush=True)
    encoder.stdin.close()
    encoder.wait()
    print(f"taglio {name}: {out} ({total:.1f} s)")
    return out


def main() -> None:
    only = set(sys.argv[1:])
    for name, cut in STORYBOARD["cuts"].items():
        if not only or name in only:
            render(name, cut)


if __name__ == "__main__":
    main()
