#!/usr/bin/env python3
"""Strict resource preflight for offline Preview 33 qualification.

Every expensive phase (candidate build VM, install VMs) must pass these
checks immediately before it starts. The rules exist because a previous
in-session execution dropped the host to ~2 GiB MemAvailable with ~4 GiB
swap in use (see hornero/releases/v0.2.0-preview32-checklist.md,
Addendum 2). Nothing here may be bypassed silently: a failed check exits
3 with an actionable diagnostic.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

GIB = 1024 * 1024  # KiB per GiB
HOST_FLOOR_GIB = 4.0  # MemAvailable that must remain while a VM runs
MIN_DISK_FREE_GIB = 10.0


@dataclass
class PreflightResult:
    ok: bool
    messages: list[str] = field(default_factory=list)

    def fail(self, message: str) -> None:
        self.ok = False
        self.messages.append(f"FAIL: {message}")

    def note(self, message: str) -> None:
        self.messages.append(f"ok: {message}")


def parse_memavailable_kib(meminfo_text: str) -> int:
    for line in meminfo_text.splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1])
    raise ValueError("MemAvailable not found in meminfo")


def parse_vmstat_swapio(vmstat_text: str) -> tuple[int, int]:
    """Last sample's (si, so) from `vmstat 1 2` output."""
    lines = [ln for ln in vmstat_text.strip().splitlines() if ln.strip() and ln.split()[0].isdigit()]
    if not lines:
        raise ValueError("no vmstat samples")
    parts = lines[-1].split()
    return int(parts[6]), int(parts[7])


def find_competing_processes(ps_text: str) -> list[str]:
    """QEMU VMs and ISO build tools that would violate one-heavy-job-at-a-time."""
    needles = ("qemu-system", "mkarchiso", "pacstrap", "mksquashfs")
    hits = []
    for line in ps_text.splitlines():
        if any(n in line for n in needles) and "grep" not in line:
            hits.append(line.strip()[:120])
    return hits


def check_resources(
    *,
    vm_mib: int,
    meminfo_text: str,
    vmstat_text: str,
    ps_text: str,
    disk_free_gib: float,
    min_disk_free_gib: float = MIN_DISK_FREE_GIB,
) -> PreflightResult:
    result = PreflightResult(ok=True)
    available_gib = parse_memavailable_kib(meminfo_text) / GIB
    required_gib = vm_mib / 1024 + HOST_FLOOR_GIB
    if available_gib < required_gib:
        result.fail(
            f"MemAvailable {available_gib:.1f} GiB < required {required_gib:.1f} GiB "
            f"(VM {vm_mib} MiB + {HOST_FLOOR_GIB:.0f} GiB host floor). "
            "Close Muse and other heavy applications, then retry."
        )
    else:
        result.note(f"MemAvailable {available_gib:.1f} GiB >= required {required_gib:.1f} GiB")
    si, so = parse_vmstat_swapio(vmstat_text)
    if si > 0 or so > 0:
        result.fail(f"swap activity in progress (si={si} so={so}); wait for the host to settle")
    else:
        result.note("no swap in/out activity in the last vmstat sample")
    competing = find_competing_processes(ps_text)
    if competing:
        result.fail(f"another heavy job is already running: {competing}")
    else:
        result.note("no competing QEMU/build processes")
    if disk_free_gib < min_disk_free_gib:
        result.fail(f"disk free {disk_free_gib:.1f} GiB < required {min_disk_free_gib:.0f} GiB")
    else:
        result.note(f"disk free {disk_free_gib:.1f} GiB")
    return result


def live_check(vm_mib: int, state_root: Path) -> PreflightResult:
    meminfo = Path("/proc/meminfo").read_text(encoding="utf-8")
    vmstat = subprocess.run(["vmstat", "1", "2"], capture_output=True, text=True, timeout=15).stdout
    ps = subprocess.run(["ps", "-eo", "args"], capture_output=True, text=True, timeout=15).stdout
    usage = shutil.disk_usage(state_root if state_root.exists() else Path.home())
    return check_resources(
        vm_mib=vm_mib,
        meminfo_text=meminfo,
        vmstat_text=vmstat,
        ps_text=ps,
        disk_free_gib=usage.free / (1024**3),
    )


def assert_floor(step: str) -> None:
    """Re-check the host floor mid-run; abort before scheduling more work."""
    available_gib = parse_memavailable_kib(Path("/proc/meminfo").read_text(encoding="utf-8")) / GIB
    if available_gib < HOST_FLOOR_GIB:
        raise SystemExit(
            f"preflight floor violated before {step}: MemAvailable {available_gib:.1f} GiB "
            f"< {HOST_FLOOR_GIB:.0f} GiB — stopping before scheduling more work (exit 3)"
        )


def main(argv: list[str]) -> int:
    vm_mib = int(argv[1]) if len(argv) > 1 else 4096
    state_root = Path(os.environ.get("OFFLINE_STATE_DIR", str(Path.home())))
    result = live_check(vm_mib=vm_mib, state_root=state_root)
    for message in result.messages:
        print(message)
    return 0 if result.ok else 3


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
