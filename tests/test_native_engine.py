from __future__ import annotations

import json

import pytest

from hornero_qa.engines.native import _virtio_gpu_device


@pytest.mark.parametrize("virgl", [False, True])
def test_virtio_gpu_enables_each_requested_output(virgl: bool) -> None:
    device = json.loads(_virtio_gpu_device(3, (1280, 800), virgl=virgl))

    assert device == {
        "driver": "virtio-vga-gl" if virgl else "virtio-vga",
        "id": "hxgpu0",
        "max_outputs": 3,
        "xres": 1280,
        "yres": 800,
        "outputs": [
            {"name": "Hornero-1", "xres": 1280, "yres": 800},
            {"name": "Hornero-2", "xres": 1280, "yres": 800},
            {"name": "Hornero-3", "xres": 1280, "yres": 800},
        ],
    }


def test_single_output_keeps_default_primary_scanout() -> None:
    device = json.loads(_virtio_gpu_device(1, (1920, 1080), virgl=False))

    assert device["max_outputs"] == 1
    assert device["xres"] == 1920
    assert device["yres"] == 1080
    assert "outputs" not in device
