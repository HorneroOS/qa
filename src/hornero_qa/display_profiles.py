"""Official display profiles and PNG dimension verification for Hornero QA."""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from PIL import Image, UnidentifiedImageError

_PNG_SIGNATURE: Final[bytes] = b"\x89PNG\r\n\x1a\n"
_RESOLUTION_RE: Final[re.Pattern[str]] = re.compile(r"^([1-9][0-9]*)x([1-9][0-9]*)$")

DEFAULT_PROFILE_NAME: Final[str] = "fhd"


class DisplayProfileError(ValueError):
    """Raised when a display profile specification or resolution is invalid."""


class PngDimensionError(DisplayProfileError):
    """Raised when a captured PNG does not match expected pixel dimensions."""


@dataclass(frozen=True)
class DisplayProfile:
    """Named virtual display geometry and scale specification."""

    name: str
    width: int
    height: int
    label: str
    scale: float = 1.0
    is_custom: bool = False

    @property
    def resolution(self) -> str:
        """Return ``WIDTHxHEIGHT`` string (or ``custom`` when unresolved)."""
        if self.width <= 0 or self.height <= 0:
            return "custom"
        return f"{self.width}x{self.height}"

    @property
    def size(self) -> tuple[int, int]:
        """Return ``(width, height)`` pixel tuple."""
        return (self.width, self.height)


DISPLAY_PROFILES: Final[dict[str, DisplayProfile]] = {
    "hd": DisplayProfile(name="hd", width=1280, height=720, label="HD (1280x720)"),
    "fhd": DisplayProfile(name="fhd", width=1920, height=1080, label="Full HD (1920x1080)"),
    "qhd": DisplayProfile(name="qhd", width=2560, height=1440, label="QHD (2560x1440)"),
    "uhd4k": DisplayProfile(name="uhd4k", width=3840, height=2160, label="4K UHD (3840x2160)"),
    "ultrawide": DisplayProfile(name="ultrawide", width=3440, height=1440, label="Ultrawide QHD (3440x1440)"),
    "vertical": DisplayProfile(
        name="vertical", width=1080, height=1920, label="Vertical Full HD (1080x1920)"
    ),
    "custom": DisplayProfile(
        name="custom", width=0, height=0, label="Custom (explicit dimensions)", is_custom=True
    ),
}

OFFICIAL_DEFAULT_PROFILE: Final[DisplayProfile] = DISPLAY_PROFILES[DEFAULT_PROFILE_NAME]


def parse_resolution(spec: str) -> tuple[int, int]:
    """Parse a ``WIDTHxHEIGHT`` string into positive integer pixel dimensions."""
    match = _RESOLUTION_RE.fullmatch(spec.strip())
    if match is None:
        raise DisplayProfileError(
            f"invalid resolution {spec!r}; expected WIDTHxHEIGHT with positive integers"
        )
    return int(match.group(1)), int(match.group(2))


def get_display_profile(
    name: str = DEFAULT_PROFILE_NAME,
    *,
    width: int | None = None,
    height: int | None = None,
    scale: float = 1.0,
) -> DisplayProfile:
    """Resolve one of the 7 official display profiles by name or ``WIDTHxHEIGHT``."""
    if scale <= 0:
        raise DisplayProfileError(f"display scale must be positive, got {scale!r}")

    key = name.strip().lower()
    if key == "custom":
        if width is None or height is None or width <= 0 or height <= 0:
            raise DisplayProfileError("custom display profile requires positive width and height")
        return DisplayProfile(
            name="custom",
            width=width,
            height=height,
            label=f"Custom ({width}x{height})",
            scale=scale,
            is_custom=True,
        )

    if key in DISPLAY_PROFILES:
        base = DISPLAY_PROFILES[key]
        if (width is not None or height is not None) and (width != base.width or height != base.height):
            raise DisplayProfileError(
                f"profile {key!r} is fixed at {base.resolution}; use 'custom' for {width}x{height}"
            )
        if scale != base.scale:
            return DisplayProfile(
                name=base.name,
                width=base.width,
                height=base.height,
                label=base.label,
                scale=scale,
                is_custom=base.is_custom,
            )
        return base

    # Allow passing an explicit WIDTHxHEIGHT string directly as a custom profile.
    if _RESOLUTION_RE.fullmatch(key):
        parsed_w, parsed_h = parse_resolution(key)
        return DisplayProfile(
            name="custom",
            width=parsed_w,
            height=parsed_h,
            label=f"Custom ({parsed_w}x{parsed_h})",
            scale=scale,
            is_custom=True,
        )

    valid = ", ".join(DISPLAY_PROFILES)
    raise DisplayProfileError(f"unknown display profile {name!r}; expected one of: {valid}")


def verify_png_dimensions(path: str | Path, expected_width: int, expected_height: int) -> tuple[int, int]:
    """Validate that ``path`` is a real PNG whose pixel dimensions match expectations exactly.

    Rejects missing files, non-PNG images, and any dimension mismatch (including upscaled or
    downscaled captures).
    """
    if expected_width <= 0 or expected_height <= 0:
        raise DisplayProfileError(
            f"expected dimensions must be positive, got {expected_width}x{expected_height}"
        )

    png_path = Path(path)
    if not png_path.is_file():
        raise FileNotFoundError(f"PNG file not found: {png_path}")

    header = png_path.read_bytes()[:24]
    if len(header) < 24 or not header.startswith(_PNG_SIGNATURE) or header[12:16] != b"IHDR":
        raise PngDimensionError(f"{png_path}: not a valid PNG file (missing PNG/IHDR header)")

    ihdr_w, ihdr_h = struct.unpack(">II", header[16:24])
    try:
        with Image.open(png_path) as img:
            if img.format != "PNG":
                raise PngDimensionError(f"{png_path}: expected PNG image, got format={img.format!r}")
            actual_w, actual_h = img.size
    except (OSError, UnidentifiedImageError) as exc:
        raise PngDimensionError(f"{png_path}: failed to decode PNG image: {exc}") from exc

    if (ihdr_w, ihdr_h) != (actual_w, actual_h):
        raise PngDimensionError(
            f"{png_path}: IHDR dimensions {ihdr_w}x{ihdr_h} disagree with decoded size {actual_w}x{actual_h}"
        )

    if (actual_w, actual_h) != (expected_width, expected_height):
        raise PngDimensionError(
            f"{png_path}: PNG dimensions {actual_w}x{actual_h} != expected {expected_width}x{expected_height}"
        )

    return actual_w, actual_h


def verify_png_profile(
    path: str | Path, profile: str | DisplayProfile = DEFAULT_PROFILE_NAME
) -> tuple[int, int]:
    """Validate that a PNG matches the resolved ``DisplayProfile`` dimensions."""
    resolved = get_display_profile(profile) if isinstance(profile, str) else profile
    if resolved.width <= 0 or resolved.height <= 0:
        raise DisplayProfileError(f"profile {resolved.name!r} has unresolved dimensions {resolved.size}")
    return verify_png_dimensions(path, resolved.width, resolved.height)


__all__ = [
    "DEFAULT_PROFILE_NAME",
    "DISPLAY_PROFILES",
    "OFFICIAL_DEFAULT_PROFILE",
    "DisplayProfile",
    "DisplayProfileError",
    "PngDimensionError",
    "get_display_profile",
    "parse_resolution",
    "verify_png_dimensions",
    "verify_png_profile",
]
