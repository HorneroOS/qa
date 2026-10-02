from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray
from PIL import Image

Img = NDArray[np.uint8]
SavePng = Callable[[Img, str], Path]


def desktop(width: int = 320, height: int = 200, seed: int = 7) -> Img:
    """A synthetic, non-blank 'desktop' frame with a bar and bar items."""
    rng = np.random.default_rng(seed)
    img = np.full((height, width, 3), (40, 30, 26), dtype=np.uint8)
    img += rng.integers(0, 6, size=img.shape, dtype=np.uint8)
    img[0:24, :] = (60, 46, 40)
    for i in range(6):
        img[6:18, 10 + 30 * i : 30 + 30 * i] = (200, 120, 80)
    return img


def paint_widget(img: Img, x: int, y: int) -> Img:
    out = img.copy()
    out[y : y + 40, x : x + 60] = (230, 220, 210)
    out[y + 8 : y + 16, x + 6 : x + 54] = (170, 82, 50)
    out[y + 22 : y + 32, x + 6 : x + 30] = (90, 60, 50)
    return out


@pytest.fixture
def save_png(tmp_path: Path) -> SavePng:
    def _save(arr: Img, name: str) -> Path:
        p = tmp_path / name
        Image.fromarray(arr).save(p)
        return p

    return _save
