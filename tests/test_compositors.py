from __future__ import annotations

import pytest

from hornero_qa.image import _compositor_packages


def test_hyprland_uses_the_base_compositor_packages() -> None:
    assert _compositor_packages("hyprland") == ()


def test_niri_image_includes_its_portal_and_xwayland_backends() -> None:
    assert _compositor_packages("niri") == (
        "niri",
        "xwayland-satellite",
        "grim",
        "rtkit",
        "xdg-desktop-portal-gnome",
        "xdg-desktop-portal-gtk",
    )


def test_labwc_is_not_misrepresented_as_supported() -> None:
    with pytest.raises(SystemExit, match="unsupported QA compositor 'labwc'"):
        _compositor_packages("labwc")
