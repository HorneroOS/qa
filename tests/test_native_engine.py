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


def test_niri_qemu_argv_is_headless_with_egl_and_virgl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess

    def forbid_hyprctl(argv: list[str], **kw: object) -> object:
        raise AssertionError(f"unexpected subprocess call: {argv}")

    monkeypatch.setattr(subprocess, "run", forbid_hyprctl)

    state = QAState(root=tmp_path / "state")
    eng = NativeEngine(state, tmp_path / "niri.qcow2", tmp_path / "runs" / "niri-1", compositor="niri")
    argv = eng.build_qemu_argv()

    display_idx = argv.index("-display")
    assert argv[display_idx + 1] == "egl-headless,gl=on"
    assert not any("gtk" in arg for arg in argv)
    assert not any("hyprctl" in arg for arg in argv)
    device_args = [argv[i + 1] for i, a in enumerate(argv) if a == "-device"]
    assert any('"driver":"virtio-vga-gl"' in d for d in device_args)

    visible_eng = NativeEngine(
        state,
        tmp_path / "niri.qcow2",
        tmp_path / "runs" / "niri-vis",
        compositor="niri",
        visible_display=True,
    )
    vis_argv = visible_eng.build_qemu_argv()
    assert vis_argv[vis_argv.index("-display") + 1] == "gtk,gl=on"


def test_hyprland_qemu_argv_uses_none_display_and_qmp_screendump(tmp_path: Path) -> None:
    state = QAState(root=tmp_path / "state")
    eng = NativeEngine(state, tmp_path / "hypr.qcow2", tmp_path / "runs" / "hypr-1", outputs=2)
    argv = eng.build_qemu_argv()

    assert argv[argv.index("-display") + 1] == "none"
    device_args = [argv[i + 1] for i, a in enumerate(argv) if a == "-device"]
    assert any('"driver":"virtio-vga"' in d and "virtio-vga-gl" not in d for d in device_args)

    class _FakeQMP:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, object]]] = []

        def screendump(self, png_path: Path) -> None:
            self.calls.append(("screendump", {"filename": str(png_path)}))

        def cmd(self, execute: str, **arguments: object) -> None:
            self.calls.append((execute, arguments))

    fake_qmp = _FakeQMP()
    eng.qmp = fake_qmp  # type: ignore[assignment]
    p0 = tmp_path / "h0.png"
    p1 = tmp_path / "h1.png"
    eng.screenshot(p0, head=0)
    eng.screenshot(p1, head=1)
    assert fake_qmp.calls == [
        ("screendump", {"filename": str(p0)}),
        ("screendump", {"filename": str(p1), "format": "png", "device": "hxgpu0", "head": 1}),
    ]
