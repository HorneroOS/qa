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
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from numpy.typing import NDArray
from PIL import Image

Array = NDArray[np.float32]
RGB = Sequence[float] | NDArray[Any]

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
    norm = np.clip(c, 0.0, 255.0) / 255.0
    out: NDArray[np.float64] = np.where(norm <= 0.04045, norm / 12.92, ((norm + 0.055) / 1.055) ** 2.4)
    return out


def rgb_to_oklab(rgb: RGB) -> tuple[float, float, float]:
    """Convert an sRGB 0..255 triple to Oklab (L, a, b)."""
    r, g, b = _srgb_to_linear(np.asarray(rgb, dtype=np.float64))
    lc = float(np.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b))
    mc = float(np.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b))
    sc = float(np.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b))
    return (
        0.2104542553 * lc + 0.7936177850 * mc - 0.0040720468 * sc,
        1.9779984951 * lc - 2.4285922050 * mc + 0.4505937099 * sc,
        0.0259040371 * lc + 0.7827717662 * mc - 0.8086757660 * sc,
    )


def oklab(rgb: Any) -> NDArray[np.float64]:
    return np.array(rgb_to_oklab(rgb), dtype=np.float64)


def delta_e_ok(rgb1: Any, rgb2: Any) -> float:
    return float(np.linalg.norm(oklab(rgb1) - oklab(rgb2)) * 100.0)


def oklab_delta_e(rgb1: RGB, rgb2: RGB) -> float:
    """Perceptual Oklab Euclidean distance (scaled by 100) between two sRGB triples."""
    return delta_e_ok(rgb1, rgb2)


def relative_luminance(rgb: Any) -> float:
    """WCAG 2.2 relative luminance for an sRGB 0..255 triple."""
    r, g, b = _srgb_to_linear(np.asarray(rgb, dtype=np.float64))
    return float(0.2126 * r + 0.7152 * g + 0.0722 * b)


def contrast_ratio(rgb1: Any, rgb2: Any) -> float:
    """WCAG 2.2 contrast ratio between two sRGB 0..255 triples (range 1.0..21.0)."""
    l1 = relative_luminance(rgb1)
    l2 = relative_luminance(rgb2)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def wcag_contrast_ratio(rgb1: RGB, rgb2: RGB) -> float:
    """WCAG 2.2 contrast ratio between two sRGB 0..255 triples (range 1.0..21.0)."""
    return contrast_ratio(rgb1, rgb2)


@dataclass(frozen=True)
class ContrastProbeResult:
    """Structured verdict for an automated WCAG 2.2 + Oklab contrast probe."""

    ok: bool
    fg_rgb: tuple[int, int, int] | None
    bg_rgb: tuple[int, int, int] | None
    contrast_ratio: float | None
    delta_e_ok: float | None
    min_ratio: float | None = None
    min_delta_e: float | None = None
    max_delta_e: float | None = None
    fg_delta_e: float | None = None
    bg_delta_e: float | None = None
    name: str | None = None
    error: str | None = None
    reason: str = "ok"

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.fg_rgb is not None:
            d["fg_rgb"] = list(self.fg_rgb)
        if self.bg_rgb is not None:
            d["bg_rgb"] = list(self.bg_rgb)
        return d


def _extract_xy(point: tuple[float, float] | Sequence[float] | dict[str, float]) -> tuple[float, float]:
    if isinstance(point, dict):
        return float(point["x"]), float(point["y"])
    return float(point[0]), float(point[1])


def _sample_patch(
    frame: Array,
    point: tuple[float, float] | Sequence[float] | dict[str, float],
    size: int,
    normalized: bool,
) -> tuple[NDArray[np.float64] | None, str | None]:
    if frame.ndim != 3 or frame.shape[2] < 3 or size <= 0:
        return None, "probe_out_of_bounds"
    fh, fw = int(frame.shape[0]), int(frame.shape[1])
    if fw <= 0 or fh <= 0:
        return None, "probe_out_of_bounds"
    raw_x, raw_y = _extract_xy(point)
    if not (math.isfinite(raw_x) and math.isfinite(raw_y)):
        return None, "probe_out_of_bounds"
    if normalized:
        if raw_x < 0.0 or raw_x > 1.0 or raw_y < 0.0 or raw_y > 1.0:
            return None, "probe_out_of_bounds"
        px = min(fw - 1, round(raw_x * fw))
        py = min(fh - 1, round(raw_y * fh))
    else:
        px = round(raw_x)
        py = round(raw_y)
        if px < 0 or py < 0 or px >= fw or py >= fh:
            return None, "probe_out_of_bounds"
    px1 = min(fw, px + size)
    py1 = min(fh, py + size)
    patch = np.asarray(frame[py:py1, px:px1, :3], dtype=np.float64).reshape(-1, 3).mean(axis=0)
    if np.isnan(patch).any():
        return None, "probe_nan"
    return patch, None


def _rgb_tuple(patch: NDArray[np.float64]) -> tuple[int, int, int]:
    r, g, b = (int(np.clip(round(float(c)), 0, 255)) for c in patch)
    return (r, g, b)


def check_contrast_probe(
    frame: Array,
    fg: tuple[float, float] | Sequence[float] | dict[str, float],
    bg: tuple[float, float] | Sequence[float] | dict[str, float],
    *,
    min_ratio: float | None = 4.5,
    min_delta_e: float | None = None,
    max_delta_e: float | None = None,
    fg_hex: str | None = None,
    bg_hex: str | None = None,
    fg_token: str | None = None,
    bg_token: str | None = None,
    tokens: dict[str, str] | None = None,
    size: int = 3,
    normalized: bool = False,
    name: str | None = None,
) -> ContrastProbeResult:
    """Sample foreground/background patches from a frame and verify WCAG 2.2 / Oklab bounds."""
    fg_patch, fg_err = _sample_patch(frame, fg, size, normalized)
    if fg_err is not None or fg_patch is None:
        return ContrastProbeResult(
            ok=False,
            fg_rgb=None,
            bg_rgb=None,
            contrast_ratio=None,
            delta_e_ok=None,
            min_ratio=min_ratio,
            min_delta_e=min_delta_e,
            max_delta_e=max_delta_e,
            name=name,
            error=fg_err,
            reason=fg_err or "probe_out_of_bounds",
        )
    bg_patch, bg_err = _sample_patch(frame, bg, size, normalized)
    if bg_err is not None or bg_patch is None:
        return ContrastProbeResult(
            ok=False,
            fg_rgb=_rgb_tuple(fg_patch),
            bg_rgb=None,
            contrast_ratio=None,
            delta_e_ok=None,
            min_ratio=min_ratio,
            min_delta_e=min_delta_e,
            max_delta_e=max_delta_e,
            name=name,
            error=bg_err,
            reason=bg_err or "probe_out_of_bounds",
        )

    ratio = round(wcag_contrast_ratio(fg_patch, bg_patch), 4)
    de = round(oklab_delta_e(fg_patch, bg_patch), 2)
    fg_rgb = _rgb_tuple(fg_patch)
    bg_rgb = _rgb_tuple(bg_patch)

    fg_want = (tokens or {}).get(fg_token) if fg_token else None
    if not fg_want:
        fg_want = fg_hex
    if fg_token and not fg_want:
        return ContrastProbeResult(
            ok=False,
            fg_rgb=fg_rgb,
            bg_rgb=bg_rgb,
            contrast_ratio=ratio,
            delta_e_ok=de,
            min_ratio=min_ratio,
            min_delta_e=min_delta_e,
            max_delta_e=max_delta_e,
            name=name,
            error="token_unresolved",
            reason="token_unresolved",
        )
    bg_want = (tokens or {}).get(bg_token) if bg_token else None
    if not bg_want:
        bg_want = bg_hex
    if bg_token and not bg_want:
        return ContrastProbeResult(
            ok=False,
            fg_rgb=fg_rgb,
            bg_rgb=bg_rgb,
            contrast_ratio=ratio,
            delta_e_ok=de,
            min_ratio=min_ratio,
            min_delta_e=min_delta_e,
            max_delta_e=max_delta_e,
            name=name,
            error="token_unresolved",
            reason="token_unresolved",
        )

    tol = 6.0 if max_delta_e is None else float(max_delta_e)
    fg_de = round(oklab_delta_e(fg_patch, hex_rgb(fg_want)), 2) if fg_want else None
    bg_de = round(oklab_delta_e(bg_patch, hex_rgb(bg_want)), 2) if bg_want else None

    failures: list[str] = []
    if min_ratio is not None and ratio < float(min_ratio):
        failures.append(f"contrast_ratio {ratio:.2f} < min_ratio {float(min_ratio):.2f}")
    if min_delta_e is not None and de < float(min_delta_e):
        failures.append(f"delta_e_ok {de:.2f} < min_delta_e {float(min_delta_e):.2f}")
    if fg_de is not None and fg_de > tol:
        failures.append(f"fg_delta_e {fg_de:.2f} > max_delta_e {tol:.2f}")
    if bg_de is not None and bg_de > tol:
        failures.append(f"bg_delta_e {bg_de:.2f} > max_delta_e {tol:.2f}")
    if max_delta_e is not None and fg_de is None and bg_de is None and de > float(max_delta_e):
        failures.append(f"delta_e_ok {de:.2f} > max_delta_e {float(max_delta_e):.2f}")

    ok = not failures
    return ContrastProbeResult(
        ok=ok,
        fg_rgb=fg_rgb,
        bg_rgb=bg_rgb,
        contrast_ratio=ratio,
        delta_e_ok=de,
        min_ratio=min_ratio,
        min_delta_e=min_delta_e,
        max_delta_e=max_delta_e,
        fg_delta_e=fg_de,
        bg_delta_e=bg_de,
        name=name,
        error=None,
        reason="ok" if ok else "; ".join(failures),
    )


def hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


HEX_RE = re.compile(r"#[0-9A-Fa-f]{6}")


def scheme_tokens(scheme_json: str) -> dict[str, str]:
    """Signal role tokens from a live scheme (schema v2, RFC 0001 §9)."""
    doc = json.loads(scheme_json)
    if doc.get("schemaVersion") != 2 or not isinstance(doc.get("palette"), dict):
        raise ValueError("not a Hornero Signal schema-v2 scheme")
    return {k: v for k, v in doc["palette"].items() if isinstance(v, str) and HEX_RE.fullmatch(v)}


def builtin_tokens(signal_qml: str, theme_id: str) -> dict[str, str]:
    """Signal role tokens of a built-in theme from the shell's services/Signal.qml."""
    m = re.search(rf'"{re.escape(theme_id)}"\s*:\s*\{{.*?"palette"\s*:\s*\{{(.*?)\}}', signal_qml, re.S)
    if not m:
        raise ValueError(f"built-in theme {theme_id} not found in Signal.qml")
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
    if anchor.ref.shape[:2] != (r["h"], r["w"]):
        raise ValueError(
            f"anchor {anchor.id} reference {anchor.ref.shape[1]}x{anchor.ref.shape[0]} "
            f"does not match region {r['w']}x{r['h']}"
        )
    x0, y0 = max(0, r["x"] - m), max(0, r["y"] - m)
    x1, y1 = min(frame.shape[1], r["x"] + r["w"] + m), min(frame.shape[0], r["y"] + r["h"] + m)
    scene = _feature(frame[y0:y1, x0:x1], anchor.mode)
    ref = _feature(anchor.ref, anchor.mode)
    if scene.shape[0] < ref.shape[0] or scene.shape[1] < ref.shape[1]:
        raise ValueError(f"anchor {anchor.id} region {r} exceeds frame {fw}x{fh}")
    # Features at the reference's own border are computed from edge padding,
    # not real neighbours: compare only pixels the filters saw identically.
    mask = np.zeros((r["h"], r["w"]), dtype=bool)
    mask[FEATURE_BORDER:-FEATURE_BORDER, FEATURE_BORDER:-FEATURE_BORDER] = True
    for mk in anchor.mask:
        mask[mk["y"] : mk["y"] + mk["h"], mk["x"] : mk["x"] + mk["w"]] = False
    n = int(mask.sum())
    if n == 0:
        raise ValueError(f"anchor {anchor.id} has no unmasked interior pixels")
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
        px0, py0 = max(0, px), max(0, py)
        px1, py1 = min(frame.shape[1], px + size), min(frame.shape[0], py + size)
        if size <= 0 or px0 >= px1 or py0 >= py1:
            probes.append({"token": p["token"], "error": "probe_out_of_bounds"})
            probe_ok = False
            continue
        patch = frame[py0:py1, px0:px1].reshape(-1, 3).mean(axis=0)
        if np.isnan(patch).any():
            probes.append({"token": p["token"], "error": "probe_nan"})
            probe_ok = False
            continue
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
