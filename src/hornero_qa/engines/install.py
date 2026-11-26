"""Install engine: QEMU/KVM + QMP for ISO-based installation acceptance.

Boots a live Hornero ISO against a fresh throwaway target disk, detects
readiness via QMP and serial console markers, and supports an explicit
ISO-detach reboot contract so post-install verification boots strictly from
the installed target disk.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path
from typing import BinaryIO

from hornero_qa.engines.native import _virtio_gpu_device, kill_scope, qmp_socket_path
from hornero_qa.keys import parse_key
from hornero_qa.qmp import QMP, QMPError
from hornero_qa.state import QAState
from hornero_qa.taxonomy import FailureClass, QAError


class InstallEngine:
    """QEMU/KVM engine for live-ISO installation and post-install reboot."""

    name = "install"

    def __init__(
        self,
        state: QAState,
        iso: Path,
        run_dir: Path,
        disk_gb: int = 20,
        mem_mb: int = 4096,
        smp: int = 2,
        firmware: str = "uefi",
        resolution: tuple[int, int] = (1280, 800),
    ) -> None:
        self.state = state
        self.iso = iso
        self.run_dir = run_dir
        self.disk_gb = disk_gb
        self.mem_mb = mem_mb
        self.smp = smp
        self.firmware = firmware
        self.resolution = resolution
        self.work = state.work_dir / run_dir.name
        self.target_disk = self.work / "target.qcow2"
        self.qmp_sock = qmp_socket_path(state.work_dir, f"install-{run_dir.name}")
        self.serial = run_dir / "logs" / "serial.log"
        self.unit = f"hornero-qa-install-{run_dir.name}"
        self.proc: subprocess.Popen[bytes] | None = None
        self.stderr: BinaryIO | None = None
        self.qmp: QMP | None = None
        self.iso_attached: bool = False

    def build_qemu_argv(self, *, attach_iso: bool = True) -> list[str]:
        """Construct the QEMU command line for live-ISO or installed-disk boot."""
        argv = [
            "systemd-run",
            "--user",
            "--scope",
            "--quiet",
            f"--unit={self.unit}",
            "-p",
            f"MemoryMax={self.mem_mb + 1024}M",
            "--",
            "qemu-system-x86_64",
            "-enable-kvm",
            "-cpu",
            "host",
            "-name",
            f"hornero-qa-install-{self.run_dir.name}",
            "-machine",
            "q35",
            "-smp",
            str(self.smp),
            "-m",
            str(self.mem_mb),
            "-device",
            _virtio_gpu_device(1, self.resolution, virgl=False),
            "-drive",
            f"file={self.target_disk},format=qcow2,if=virtio",
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
        if attach_iso:
            argv.extend(
                [
                    "-drive",
                    f"file={self.iso},media=cdrom,readonly=on,if=ide",
                    "-boot",
                    "order=dc",
                ]
            )
        else:
            argv.extend(["-boot", "order=c"])
        return argv

    def start(self, *, attach_iso: bool = True) -> None:
        if attach_iso and not self.iso.exists():
            raise QAError(FailureClass.PROVISIONING, f"installer ISO missing: {self.iso}")
        self.work.mkdir(parents=True, exist_ok=True)
        self.serial.parent.mkdir(parents=True, exist_ok=True)
        if not self.target_disk.exists():
            subprocess.run(
                [
                    "qemu-img",
                    "create",
                    "-q",
                    "-f",
                    "qcow2",
                    str(self.target_disk),
                    f"{self.disk_gb}G",
                ],
                check=True,
            )
        self.qmp_sock.unlink(missing_ok=True)
        self.iso_attached = attach_iso
        argv = self.build_qemu_argv(attach_iso=attach_iso)
        self.stderr = (self.run_dir / "logs" / "qemu.stderr").open("ab")
        self.proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=self.stderr)
        try:
            self.qmp = QMP.wait(self.qmp_sock, deadline_s=30)
        except QMPError as exc:
            raise QAError(FailureClass.BOOT, f"Install QEMU did not start: {exc}") from exc

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def serial_text(self) -> str:
        return self.serial.read_text(encoding="utf-8", errors="replace") if self.serial.exists() else ""

    def wait_serial_marker(self, marker: str, *, timeout_s: float = 120.0, poll_s: float = 0.5) -> bool:
        """Poll serial.log until `marker` appears or timeout expires."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if marker in self.serial_text():
                return True
            if not self.alive():
                return False
            time.sleep(poll_s)
        return marker in self.serial_text()

    def detach_iso_and_reboot(
        self, *, ready_marker: str = "login:", timeout_s: float = 120.0, poll_s: float = 0.5
    ) -> bool:
        """Stop live-ISO boot, detach ISO media, and boot the installed target disk."""
        self.stop(keep_disk=True)
        self.start(attach_iso=False)
        return self.wait_serial_marker(ready_marker, timeout_s=timeout_s, poll_s=poll_s)

    def screenshot(self, dest: Path) -> Path:
        if self.qmp is None:
            raise QAError(FailureClass.HARNESS, "InstallEngine QMP is not connected")
        dest.parent.mkdir(parents=True, exist_ok=True)
        self.qmp.screendump(dest)
        return dest

    def key(self, chord: str) -> None:
        if self.qmp is None:
            raise QAError(FailureClass.HARNESS, "InstallEngine QMP is not connected")
        self.qmp.chord(parse_key(chord))

    def stop(self, *, keep_disk: bool = False) -> None:
        if self.qmp is not None:
            self.qmp.quit()
            self.qmp = None
        if self.proc is not None:
            try:
                self.proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
            self.proc = None
        kill_scope(self.unit)
        if self.stderr is not None:
            self.stderr.close()
            self.stderr = None
        self.qmp_sock.unlink(missing_ok=True)
        self.iso_attached = False
        if not keep_disk:
            shutil.rmtree(self.work, ignore_errors=True)
