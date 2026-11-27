from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from hornero_qa import image
from hornero_qa.image import _compositor_packages
from hornero_qa.state import QAState


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


def test_image_refresh_closes_log_handle_and_exports_horneroctl_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = QAState(root=tmp_path / "state")
    base = tmp_path / "base.qcow2"
    base.write_bytes(b"qcow2")
    shell = tmp_path / "shell"
    (shell / "tests/vm/lib").mkdir(parents=True)
    (shell / "tests/vm/lib/deploy-shell.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    ctl = tmp_path / "horneroctl"
    ctl.write_text("#!/bin/sh\n", encoding="utf-8")

    opened_logs: list[Any] = []
    orig_open = Path.open

    def tracking_open(self: Path, *args: Any, **kwargs: Any) -> Any:
        handle = orig_open(self, *args, **kwargs)
        if self.name == "qemu.log":
            opened_logs.append(handle)
        return handle

    monkeypatch.setattr(Path, "open", tracking_open)

    seen_envs: list[dict[str, str]] = []

    class _FakeProc:
        def poll(self) -> int | None:
            return None

        def kill(self) -> None:
            pass

        def wait(self, timeout: float | None = None) -> int:
            return 0

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if argv[:2] == ["git", "-C"]:
            out = "deadbeef\n" if "rev-parse" in argv else ""
            return subprocess.CompletedProcess(argv, 0, stdout=out, stderr="")
        if argv[0] == "bash":
            seen_envs.append(dict(kwargs["env"]))
            raise RuntimeError("stop after deploy")
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: _FakeProc())
    monkeypatch.setattr(image, "_ssh", lambda *a, **kw: None)

    with pytest.raises(RuntimeError, match="stop after deploy"):
        image.refresh(state, base, shell, "a" * 40, ctl, "test-img")

    assert len(opened_logs) == 1
    assert opened_logs[0].closed is True
    assert seen_envs[0]["HX_HORNEROCTL_BIN"] == str(ctl)
    assert seen_envs[0]["HX_HOREROCTL_BIN"] == str(ctl)
