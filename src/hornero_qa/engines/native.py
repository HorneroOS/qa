"""Native engine: QEMU/KVM + QMP on a Hornero QA ready image.

- Every run boots a throwaway qcow2 overlay of the ready image (the image is
  never written), inside a memory-capped `systemd-run --user --scope`.
- Action lane: QMP HID keyboard and USB-tablet events (`hornero_qa.qmp`).
- Observation lane: QMP `screendump` per head, read-only SSH probes, logs.
"""

from __future__ import annotations

import contextlib
import json
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from hornero_qa.keys import parse_key, text_to_chords
from hornero_qa.qmp import QMP, QMPError
from hornero_qa.state import QAState
from hornero_qa.taxonomy import FailureClass, QAError


@dataclass
class ProbeResult:
    rc: int
    stdout: str
    stderr: str


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


class NativeEngine:
    name = "native"

    def __init__(
        self,
        state: QAState,
        image: Path,
        run_dir: Path,
        outputs: int = 1,
        resolution: tuple[int, int] = (1280, 800),
        mem_mb: int = 2048,
        smp: int = 2,
    ) -> None:
        self.state = state
        self.image = image
        self.run_dir = run_dir
        self.outputs = outputs
        self.resolution = resolution
        self.mem_mb = mem_mb
        self.smp = smp
        self.work = state.work_dir / run_dir.name
        self.overlay = self.work / "disk.qcow2"
        self.qmp_sock = self.work / "qmp.sock"
        self.serial = run_dir / "logs" / "serial.log"
        self.ssh_port = _free_port()
        self.unit = f"hornero-qa-{run_dir.name}"
        self.proc: subprocess.Popen[bytes] | None = None
        self.stderr: BinaryIO | None = None
        self.qmp: QMP | None = None

    # ------------------------------------------------------------ lifecycle --
    def start(self) -> None:
        if not self.image.exists():
            raise QAError(FailureClass.PROVISIONING, f"ready image missing: {self.image}")
        self.work.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "qemu-img",
                "create",
                "-q",
                "-f",
                "qcow2",
                "-F",
                "qcow2",
                "-b",
                str(self.image),
                str(self.overlay),
            ],
            check=True,
        )
        w, h = self.resolution
        argv = [
            "systemd-run",
            "--user",
            "--scope",
            "--quiet",
            f"--unit={self.unit}",
            "-p",
            f"MemoryMax={self.mem_mb + 700}M",
            "--",
            "qemu-system-x86_64",
            "-enable-kvm",
            "-cpu",
            "host",
            "-machine",
            "q35",
            "-smp",
            str(self.smp),
            "-m",
            str(self.mem_mb),
            "-device",
            f"virtio-vga,max_outputs={self.outputs},xres={w},yres={h}",
            "-drive",
            f"file={self.overlay},format=qcow2,if=virtio",
            "-netdev",
            f"user,id=net0,restrict=on,hostfwd=tcp:127.0.0.1:{self.ssh_port}-:22",
            "-device",
            "virtio-net-pci,netdev=net0",
            "-display",
            "none",
            "-serial",
            f"file:{self.serial}",
            "-qmp",
            f"unix:{self.qmp_sock},server,nowait",
            "-usb",
            "-device",
            "qemu-xhci",
            "-device",
            "usb-tablet",
            "-device",
            "usb-kbd",
        ]
        self.stderr = (self.run_dir / "logs" / "qemu.stderr").open("wb")
        self.proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=self.stderr)
        try:
            self.qmp = QMP.wait(self.qmp_sock, deadline_s=30)
        except QMPError as exc:
            raise QAError(FailureClass.BOOT, f"QEMU did not start: {exc}") from exc

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def stop(self) -> None:
        if self.qmp:
            self.qmp.quit()
            self.qmp = None
        if self.proc:
            try:
                self.proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
            self.proc = None
        # Belt and braces: the scope dies with QEMU, but a half-started run
        # (QMP never answered) must not leave anything behind.
        kill_scope(self.unit)
        if self.stderr is not None:
            self.stderr.close()
            self.stderr = None
        shutil.rmtree(self.work, ignore_errors=True)

    # ---------------------------------------------------------- observation --
    def screenshot(self, dest: Path, head: int = 0) -> Path:
        q = self._q()
        dest.parent.mkdir(parents=True, exist_ok=True)
        if head == 0:
            q.screendump(dest)
        else:
            q.cmd("screendump", filename=str(dest), format="png", device="video0", head=head)
        return dest

    def probe(self, command: str, timeout: float = 20.0) -> ProbeResult:
        """Read-only guest probe over SSH in the user's session environment."""
        # UTF-8 locale: Qt prints a locale warning on stdout under C, which would pollute probes.
        env = (
            "export LANG=C.UTF-8 LC_ALL=C.UTF-8 XDG_RUNTIME_DIR=/run/user/$(id -u) WAYLAND_DISPLAY=wayland-1 "
            'HYPRLAND_INSTANCE_SIGNATURE="$(ls -t /run/user/$(id -u)/hypr 2>/dev/null | head -1)"; '
        )
        argv = [
            "ssh",
            "-4",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "LogLevel=ERROR",
            "-o",
            "ConnectTimeout=5",
            "-o",
            "BatchMode=yes",
            "-i",
            str(self.state.ssh_key),
            "-p",
            str(self.ssh_port),
            f"{self.state.guest_user}@127.0.0.1",
            env + command,
        ]
        try:
            r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return ProbeResult(124, "", "probe timeout")
        return ProbeResult(r.returncode, r.stdout.strip(), r.stderr.strip())

    def wait_ssh(self, timeout: float = 120.0) -> bool:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if not self.alive():
                return False
            if self.probe("true", timeout=8).rc == 0:
                return True
            time.sleep(1.0)
        return False

    def serial_text(self) -> str:
        try:
            return self.serial.read_text(errors="replace")
        except OSError:
            return ""

    def collect_logs(self) -> None:
        logs = self.run_dir / "logs"
        for name, cmd in {
            "quickshell.log": "cat /tmp/qs.log",
            "hyprland.log": "cat /tmp/hypr.log",
            "journal.log": "journalctl -b --no-pager -n 400",
            "processes.txt": "ps -eo pid,comm,args --sort=pid | head -200",
        }.items():
            r = self.probe(cmd, timeout=20)
            (logs / name).write_text(r.stdout if r.rc == 0 else f"[probe failed rc={r.rc}] {r.stderr}\n")

    # ---------------------------------------------------------------- input --
    def key(self, spec: str) -> None:
        self._q().chord(parse_key(spec))

    def type_text(self, text: str) -> None:
        for chord in text_to_chords(text):
            self._q().chord(chord, hold_s=0.02)
            time.sleep(0.02)

    def pointer(self, x: float, y: float, click: str | None = None, glide: int = 1) -> None:
        q = self._q()
        if glide > 1:
            # Glide from the current position is unknown to QMP; approach from
            # straight above so hover-entry happens like a real pointer.
            for i in range(1, glide + 1):
                q.pointer_abs(x, max(0.0, y - 0.05 * (glide - i) / glide))
                time.sleep(0.02)
        q.pointer_abs(x, y)
        if click:
            time.sleep(0.05)
            q.click(click)

    def scroll(self, steps: int) -> None:
        self._q().scroll(steps)

    def _q(self) -> QMP:
        if self.qmp is None:
            raise QAError(FailureClass.HARNESS, "engine not started")
        return self.qmp


def write_image_info(image: Path, info: dict[str, object]) -> None:
    image.with_suffix(".json").write_text(json.dumps(info, indent=2) + "\n")


def read_image_info(image: Path) -> dict[str, object]:
    p = image.with_suffix(".json")
    if not p.exists():
        return {}
    data: dict[str, object] = json.loads(p.read_text())
    return data


def kill_scope(unit: str) -> None:
    with contextlib.suppress(FileNotFoundError):
        subprocess.run(["systemctl", "--user", "stop", f"{unit}.scope"], capture_output=True, check=False)


__all__ = ["NativeEngine", "ProbeResult", "kill_scope", "read_image_info", "write_image_info"]
