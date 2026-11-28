"""Tests for official display profiles and PNG dimension verification."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from hornero_qa.display_profiles import (
    DEFAULT_PROFILE_NAME,
    DISPLAY_PROFILES,
    OFFICIAL_DEFAULT_PROFILE,
    DisplayProfileError,
    PngDimensionError,
    get_display_profile,
    parse_resolution,
    verify_png_dimensions,
    verify_png_profile,
)


def test_official_display_profiles_complete() -> None:
    expected = {
        "hd": (1280, 720),
        "fhd": (1920, 1080),
        "qhd": (2560, 1440),
        "uhd4k": (3840, 2160),
        "ultrawide": (3440, 1440),
        "vertical": (1080, 1920),
        "custom": (0, 0),
    }
    assert set(DISPLAY_PROFILES) == set(expected)
    for name, dims in expected.items():
        assert DISPLAY_PROFILES[name].size == dims

    assert DEFAULT_PROFILE_NAME == "fhd"
    assert OFFICIAL_DEFAULT_PROFILE.name == "fhd"
    assert OFFICIAL_DEFAULT_PROFILE.size == (1920, 1080)
    assert OFFICIAL_DEFAULT_PROFILE.resolution == "1920x1080"


@pytest.mark.parametrize(
    ("name", "expected_size", "expected_res"),
    [
        ("hd", (1280, 720), "1280x720"),
        ("fhd", (1920, 1080), "1920x1080"),
        ("qhd", (2560, 1440), "2560x1440"),
        ("uhd4k", (3840, 2160), "3840x2160"),
        ("ultrawide", (3440, 1440), "3440x1440"),
        ("vertical", (1080, 1920), "1080x1920"),
    ],
)
def test_get_display_profile_named(name: str, expected_size: tuple[int, int], expected_res: str) -> None:
    profile = get_display_profile(name)
    assert profile.size == expected_size
    assert profile.resolution == expected_res
    assert profile.scale == 1.0
    assert not profile.is_custom


def test_custom_display_profile_resolution() -> None:
    p1 = get_display_profile("custom", width=1600, height=900, scale=1.5)
    assert p1.name == "custom"
    assert p1.size == (1600, 900)
    assert p1.resolution == "1600x900"
    assert p1.scale == 1.5
    assert p1.is_custom

    p2 = get_display_profile("1440x900")
    assert p2.name == "custom"
    assert p2.size == (1440, 900)
    assert p2.is_custom

    assert parse_resolution("3840x2160") == (3840, 2160)


def test_get_display_profile_rejects_invalid_inputs() -> None:
    with pytest.raises(DisplayProfileError, match="custom display profile requires"):
        get_display_profile("custom")

    with pytest.raises(DisplayProfileError, match="fixed at 1920x1080"):
        get_display_profile("fhd", width=1280, height=800)

    with pytest.raises(DisplayProfileError, match="unknown display profile"):
        get_display_profile("8k-nonexistent")

    with pytest.raises(DisplayProfileError, match="scale must be positive"):
        get_display_profile("fhd", scale=0)

    with pytest.raises(DisplayProfileError, match="invalid resolution"):
        parse_resolution("0x1080")


def test_verify_png_dimensions_passes_exact_match(tmp_path: Path) -> None:
    fhd = tmp_path / "fhd.png"
    Image.new("RGB", (1920, 1080), (16, 24, 32)).save(fhd)
    assert verify_png_dimensions(fhd, 1920, 1080) == (1920, 1080)
    assert verify_png_profile(fhd, "fhd") == (1920, 1080)

    uhd = tmp_path / "4k.png"
    Image.new("RGB", (3840, 2160), (16, 24, 32)).save(uhd)
    assert verify_png_profile(uhd, "uhd4k") == (3840, 2160)


def test_verify_png_dimensions_rejects_mismatch_and_non_png(tmp_path: Path) -> None:
    hd_path = tmp_path / "hd-not-fhd.png"
    Image.new("RGB", (1280, 800), (16, 24, 32)).save(hd_path)

    with pytest.raises(PngDimensionError, match="1280x800 != expected 1920x1080"):
        verify_png_dimensions(hd_path, 1920, 1080)

    with pytest.raises(PngDimensionError, match="1280x800 != expected 3840x2160"):
        verify_png_profile(hd_path, "uhd4k")

    jpg_path = tmp_path / "fake.png"
    Image.new("RGB", (1920, 1080), (16, 24, 32)).save(jpg_path, format="JPEG")
    with pytest.raises(PngDimensionError, match="not a valid PNG file"):
        verify_png_dimensions(jpg_path, 1920, 1080)

    with pytest.raises(FileNotFoundError):
        verify_png_dimensions(tmp_path / "missing.png", 1920, 1080)

    with pytest.raises(DisplayProfileError, match="unresolved dimensions"):
        verify_png_profile(hd_path, DISPLAY_PROFILES["custom"])
