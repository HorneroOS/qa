"""Frame maths: screen-change/stability detection and `hornero.anchor/1` matching.

Screen synchronization follows os-autoinst semantics (compare consecutive
frames by PSNR) but on downscaled luminance with optional ignore regions, so a
ticking clock does not block "stable". Anchors are small theme-stable crops
matched by ZNCC (luminance or Sobel structure) inside a search margin, plus a
bad-pixel check and Oklab colour probes resolved from design tokens. Unlike
os-autoinst needles, the search never widens to the whole screen and colour
is checked, so offset-only and colour-only regressions are detected.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from numpy.typing import NDArray
from PIL import Image

Array = NDArray[np.float32]

ANCHOR_SCHEMA = "hornero.anchor/1"
DEFAULT_THRESHOLDS: dict[str, dict[str, float]] = {
    "structure": {"zncc": 0.92, "bad_pixel_frac": 0.03, "bad_pixel_delta": 32},
    "pixel": {"zncc": 0.95, "bad_pixel_frac": 0.03, "bad_pixel_delta": 32},
}
ABSENT_GAP = 0.15
FEATURE_BORDER = 2  # blur3 + sobel reach: two pixels of padding influence


# ------------------------------------------------------------------ frames --
def load_frame(path: str | Path) -> Array:
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.float32)


def luminance(rgb: Array) -> Array:
    out: Array = rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722
    return out


def frame_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def blank_frame(rgb: Array) -> bool:
    """Same gate as shell tests/vm/lib/check_screenshot.py (>=16 colours, luma sd >= 3)."""
    small = rgb[::4, ::4].astype(np.uint8).reshape(-1, 3).astype(np.uint32)
    colours = len(np.unique(small[:, 0] << 16 | small[:, 1] << 8 | small[:, 2]))
    return colours < 16 or float(luminance(rgb).std()) < 3.0


@dataclass(frozen=True)
class Rect:
    """A rectangle in normalized output coordinates (0..1)."""

    x: float
    y: float
    w: float
    h: float

    def pixels(self, width: int, height: int) -> tuple[int, int, int, int]:
        return (
            round(self.x * width),
            round(self.y * height),
            max(1, round(self.w * width)),
            max(1, round(self.h * height)),
        )


def _comparable(rgb: Array, ignore: list[Rect], step: int = 4) -> Array:
    lum = luminance(rgb).copy()
    h, w = lum.shape
    for r in ignore:
        x, y, rw, rh = r.pixels(w, h)
        lum[y : y + rh, x : x + rw] = 0.0
    small: Array = lum[::step, ::step]
    return small


def psnr(a: Array, b: Array, ignore: list[Rect] | None = None) -> float:
    """PSNR in dB between two frames (inf when identical)."""
    if a.shape != b.shape:
        return 0.0
    ca, cb = _comparable(a, ignore or []), _comparable(b, ignore or [])
    mse = float(np.mean((ca - cb) ** 2))
    if mse == 0.0:
        return math.inf
    return 10.0 * math.log10(255.0**2 / mse)


# Thresholds: os-autoinst uses ~50 dB for "changed" and ~47 dB for "still"
# on full RGB frames; on downscaled luminance a smaller tolerance band works.
CHANGED_BELOW_DB = 45.0
STILL_ABOVE_DB = 50.0


def changed(a: Array, b: Array, ignore: list[Rect] | None = None) -> bool:
    return psnr(a, b, ignore) < CHANGED_BELOW_DB


def still(a: Array, b: Array, ignore: list[Rect] | None = None) -> bool:
    return psnr(a, b, ignore) >= STILL_ABOVE_DB


# ------------------------------------------------------------------ colour --
def _srgb_to_linear(c: NDArray[np.float64]) -> NDArray[np.float64]:
    c = c / 255.0
    out: NDArray[np.float64] = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return out


def oklab(rgb: Any) -> NDArray[np.float64]:
    r, g, b = _srgb_to_linear(np.asarray(rgb, dtype=np.float64))
    lc = np.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b)
    mc = np.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b)
    sc = np.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
    return np.array(
        [
            0.2104542553 * lc + 0.7936177850 * mc - 0.0040720468 * sc,
            1.9779984951 * lc - 2.4285922050 * mc + 0.4505937099 * sc,
            0.0259040371 * lc + 0.7827717662 * mc - 0.8086757660 * sc,
        ]
    )


def delta_e_ok(rgb1: Any, rgb2: Any) -> float:
    return float(np.linalg.norm(oklab(rgb1) - oklab(rgb2)) * 100.0)


def hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def load_tokens(colours_qml: str | Path, table: str = "_horneroDark") -> dict[str, str]:
    """Resolve design tokens from the shell's services/Colours.qml token table."""
    src = Path(colours_qml).read_text(encoding="utf-8")
    m = re.search(rf"{table}\s*:\s*\(\{{(.*?)\}}\)", src, re.S)
    if not m:
        raise ValueError(f"token table {table} not found in {colours_qml}")
    return dict(re.findall(r'"(\w+)"\s*:\s*"(#[0-9A-Fa-f]{6})"', m.group(1)))


# ------------------------------------------------------------------ anchors --
def _blur3(a: Array) -> Array:
    k = (0.25, 0.5, 0.25)
    p = np.pad(a, 1, mode="edge")
    h = p[:, :-2] * k[0] + p[:, 1:-1] * k[1] + p[:, 2:] * k[2]
    out: Array = h[:-2] * k[0] + h[1:-1] * k[1] + h[2:] * k[2]
    return out


def _sobel(a: Array) -> Array:
    p = np.pad(a, 1, mode="edge")
    gx = (p[:-2, 2:] + 2 * p[1:-1, 2:] + p[2:, 2:]) - (p[:-2, :-2] + 2 * p[1:-1, :-2] + p[2:, :-2])
    gy = (p[2:, :-2] + 2 * p[2:, 1:-1] + p[2:, 2:]) - (p[:-2, :-2] + 2 * p[:-2, 1:-1] + p[:-2, 2:])
    out: Array = np.abs(gx) + np.abs(gy)
    return out


def _feature(rgb: Array, mode: str) -> Array:
    y = _blur3(luminance(rgb.astype(np.float32)))
    return _sobel(y) if mode == "structure" else y


@dataclass
class Anchor:
    id: str
    tags: list[str]
    frame: dict[str, int]
    region: dict[str, int]
    margin: int = 24
    mode: str = "structure"
    mask: list[dict[str, int]] = field(default_factory=list)
    thresholds: dict[str, float] = field(default_factory=dict)
    color_probes: list[dict[str, Any]] = field(default_factory=list)
    variant: dict[str, str] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    ref: Array | None = None

    @classmethod
    def load(cls, path: str | Path) -> Anchor:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if data.get("schema") != ANCHOR_SCHEMA:
            raise ValueError(f"{path}: schema {data.get('schema')!r} != {ANCHOR_SCHEMA}")
        keys = {f for f in cls.__dataclass_fields__ if f != "ref"}
        anchor = cls(**{k: v for k, v in data.items() if k in keys})
        anchor.ref = load_frame(Path(path).with_suffix(".png"))
        return anchor


@dataclass
class AnchorResult:
    id: str
    expect: str
    verdict: bool
    zncc: float
    bad_pixel_frac: float
    offset: tuple[int, int]
    probes: list[dict[str, Any]]
    reason: str

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["offset"] = list(self.offset)
        return d


def match_anchor(
    anchor: Anchor, frame: Array, expect: str = "present", tokens: dict[str, str] | None = None
) -> AnchorResult:
    if anchor.ref is None:
        raise ValueError(f"anchor {anchor.id} has no reference image")
    fw, fh = anchor.frame["width"], anchor.frame["height"]
    if frame.shape[1] != fw or frame.shape[0] != fh:
        raise ValueError(f"resolution mismatch: frame {frame.shape[1]}x{frame.shape[0]} != anchor {fw}x{fh}")
    th = DEFAULT_THRESHOLDS[anchor.mode] | anchor.thresholds
    r, m = anchor.region, anchor.margin
    x0, y0 = max(0, r["x"] - m), max(0, r["y"] - m)
    x1, y1 = min(frame.shape[1], r["x"] + r["w"] + m), min(frame.shape[0], r["y"] + r["h"] + m)
    scene = _feature(frame[y0:y1, x0:x1], anchor.mode)
    ref = _feature(anchor.ref, anchor.mode)
    # Features at the reference's own border are computed from edge padding,
    # not real neighbours: compare only pixels the filters saw identically.
    mask = np.zeros((r["h"], r["w"]), dtype=bool)
    mask[FEATURE_BORDER:-FEATURE_BORDER, FEATURE_BORDER:-FEATURE_BORDER] = True
    for mk in anchor.mask:
        mask[mk["y"] : mk["y"] + mk["h"], mk["x"] : mk["x"] + mk["w"]] = False
    n = int(mask.sum())
    rv = ref[mask]
    rz = rv - rv.mean()
    rnorm = float(np.sqrt((rz**2).sum()))
    win = sliding_window_view(scene, ref.shape)
    scores = np.full(win.shape[:2], -1.0, dtype=np.float64)
    for iy in range(win.shape[0]):
        w = win[iy][:, mask]
        wz = w - w.mean(axis=1, keepdims=True)
        den = np.sqrt((wz**2).sum(axis=1)) * rnorm
        num = wz @ rz
        with np.errstate(invalid="ignore", divide="ignore"):
            scores[iy] = np.where(den > 1e-6, num / den, 0.0)
    best = float(scores.max())
    cand = np.argwhere(scores >= best - 0.005)
    ox, oy = r["x"] - x0, r["y"] - y0
    iy, ix = min(cand, key=lambda p: (int(p[0]) - oy) ** 2 + (int(p[1]) - ox) ** 2)
    off = (int(x0 + ix - r["x"]), int(y0 + iy - r["y"]))
    mx, my = r["x"] + off[0], r["y"] + off[1]
    crop = frame[my : my + r["h"], mx : mx + r["w"]]
    bad = float(
        (np.abs(luminance(crop) - luminance(anchor.ref))[mask] > th["bad_pixel_delta"]).sum() / max(1, n)
    )
    probes: list[dict[str, Any]] = []
    probe_ok = True
    for p in anchor.color_probes:
        size = int(p.get("size", 3))
        px, py = mx + int(p["at"]["x"]), my + int(p["at"]["y"])
        patch = frame[py : py + size, px : px + size].reshape(-1, 3).mean(axis=0)
        want = (tokens or {}).get(p["token"]) or p.get("fallback_hex")
        if not want:
            probes.append({"token": p["token"], "error": "token_unresolved"})
            probe_ok = False
            continue
        de = delta_e_ok(patch, hex_rgb(want))
        ok = de <= float(p.get("max_delta_e", 6.0))
        probe_ok &= ok
        got = "#{:02x}{:02x}{:02x}".format(*(round(float(c)) for c in patch))
        probes.append({"token": p["token"], "want": want, "got": got, "delta_e_ok": round(de, 2), "ok": ok})
    if expect == "present":
        struct_ok = best >= th["zncc"] and bad <= th["bad_pixel_frac"]
        verdict = struct_ok and probe_ok
        if verdict:
            reason = "ok"
        elif struct_ok:
            reason = "colour_probe"
        else:
            reason = "zncc" if best < th["zncc"] else "bad_pixels"
    else:
        verdict = best < th["zncc"] - ABSENT_GAP
        reason = "ok" if verdict else "still_present"
    return AnchorResult(anchor.id, expect, bool(verdict), round(best, 4), round(bad, 4), off, probes, reason)


def cut_anchor(
    frame_path: str | Path,
    out_dir: str | Path,
    anchor_id: str,
    rect: tuple[int, int, int, int],
    tags: list[str],
    mode: str = "structure",
    margin: int = 24,
    provenance: dict[str, Any] | None = None,
) -> Path:
    """Cut a reference crop from a certified frame and write anchor JSON + PNG."""
    img = Image.open(frame_path).convert("RGB")
    x, y, w, h = rect
    out = Path(out_dir)
    png = out / f"{anchor_id}.png"  # ids are namespaced: launcher/search-field
    png.parent.mkdir(parents=True, exist_ok=True)
    img.crop((x, y, x + w, y + h)).save(png)
    data = {
        "schema": ANCHOR_SCHEMA,
        "id": anchor_id,
        "tags": tags,
        "frame": {"width": img.width, "height": img.height, "scale": 1},
        "region": {"x": x, "y": y, "w": w, "h": h},
        "margin": margin,
        "mode": mode,
        "mask": [],
        "thresholds": DEFAULT_THRESHOLDS[mode],
        "color_probes": [],
        "provenance": (provenance or {}) | {"capture_sha256": frame_sha256(frame_path)},
    }
    path = out / f"{anchor_id}.json"
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path
