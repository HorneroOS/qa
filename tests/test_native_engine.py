from __future__ import annotations

import json
from pathlib import Path

import pytest

from hornero_qa.engines.native import NativeEngine, ProbeResult, _virtio_gpu_device
from hornero_qa.state import QAState


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


def test_niri_screenshot_quotes_remote_path_and_probe_discovers_wayland_display(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess

    state = QAState(root=tmp_path / "state")
    run_dir = tmp_path / "runs" / "run with spaces"
    eng = NativeEngine(state, tmp_path / "img.qcow2", run_dir, compositor="niri")
    eng.qmp = object()  # type: ignore[assignment]

    captured_cmds: list[str] = []

    def fake_probe(command: str, timeout: float = 20.0) -> ProbeResult:
        captured_cmds.append(command)
        return ProbeResult(0, "", "")

    monkeypatch.setattr(eng, "probe", fake_probe)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess(a[0], 0, stdout="", stderr=""),
    )
    eng.screenshot(tmp_path / "out.png", head=0)
    assert captured_cmds == ["grim '/tmp/hornero-qa-run with spaces-frame.png'"]

    ssh_argvs: list[list[str]] = []

    def fake_run(argv: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
        ssh_argvs.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    eng2 = NativeEngine(state, tmp_path / "img.qcow2", tmp_path / "runs" / "r1")
    eng2.probe("true")
    remote_cmd = ssh_argvs[0][-1]
    assert "WAYLAND_DISPLAY=wayland-1 " not in remote_cmd
    assert "wayland-[0-9]*" in remote_cmd
    assert 'WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-${wayland_sock:-wayland-1}}"' in remote_cmd


def test_hyprland_guest_config_uses_preferred_mode() -> None:
    lua = (Path(__file__).resolve().parents[1] / "guest" / "hyprland.lua").read_text(encoding="utf-8")
    assert 'mode = "1280x800@60"' not in lua
    assert lua.count('mode = "preferred"') >= 3
