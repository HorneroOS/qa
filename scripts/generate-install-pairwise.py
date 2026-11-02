#!/usr/bin/env python3
"""Render the pairwise install scenarios from install_matrix.

Run: uv run python scripts/generate-install-pairwise.py
The generated YAML is committed; tests fail if it drifts.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hornero_qa.install_matrix import (
    STUDIO_COMPLETE,
    Selection,
    esp_recommended_mib,
    pairwise_rows,
)

OUT = Path(__file__).resolve().parents[1] / "scenarios" / "install-pairwise"


def _probe(note: str, run: str, **kw: str) -> dict[str, Any]:
    return {"note": note, "probe": {"run": run, **kw}}


def render(sel: Selection) -> dict[str, Any]:
    kernels = list(sel.kernel_packages)
    esp = esp_recommended_mib(sel)
    bt = "enabled" if sel.bluetooth else "disabled"
    fallback_note = (
        " On the reboot into the installed system, choose the linux-lts boot entry."
        if sel.kernels == "dual-primary-lts"
        else ""
    )
    proof: list[dict[str, Any]] = [
        _probe(
            "Installed Hyprland session is running after authenticating at the greeter",
            "pgrep -x Hyprland >/dev/null && echo up",
            equals="up",
        ),
        _probe(
            "Installed profile metadata names the installed edition",
            "python3 -c \"import json;print(json.load(open('/usr/lib/hornero/system-profile.json'))"
            "['edition']['edition'])\"",
            equals=sel.edition,
        ),
        _probe(
            "horneroctl system info agrees with the installed profile",
            "horneroctl system info --json | python3 -c "
            "\"import json,sys;print(json.load(sys.stdin)['data']['edition'])\"",
            equals=sel.edition,
        ),
        _probe(
            "Installer package repository removed from pacman.conf (cleanup contract)",
            "grep -c hornero-installer /etc/pacman.conf; true",
            equals="0",
        ),
        _probe(
            "Firmware of the installed boot matches the declared firmware",
            "[ -d /sys/firmware/efi ] && echo uefi || echo bios",
            equals=sel.firmware,
        ),
    ]
    for kernel in kernels:
        proof.append(
            _probe(
                f"Kernel {kernel} image, initramfs, fallback initramfs and headers are installed",
                f"test -f /boot/vmlinuz-{kernel} && test -f /boot/initramfs-{kernel}.img && "
                f"test -f /boot/initramfs-{kernel}-fallback.img && "
                f"pacman -Qq {kernel} {kernel}-headers >/dev/null && echo ok",
                equals="ok",
            )
        )
    if sel.primary_kernel == "linux-lts":
        proof.append(_probe("Running kernel is the LTS primary/fallback", "uname -r", contains="lts"))
    else:
        proof.append(_probe("Running kernel is not the LTS kernel", "uname -r", not_contains="lts"))
    if sel.bootloader == "grub":
        entries = " && ".join(f"grep -q vmlinuz-{k} /boot/grub/grub.cfg" for k in kernels)
        proof.append(
            _probe(
                "GRUB config has a menuentry covering every installed kernel",
                f"grep -q menuentry /boot/grub/grub.cfg && {entries} && echo ok",
                equals="ok",
            )
        )
    else:
        entries = " && ".join(f"grep -rq vmlinuz-{k} /boot/loader/entries/" for k in kernels)
        proof.append(
            _probe(
                "systemd-boot loader and an entry covering every installed kernel exist",
                f"test -f /boot/loader/loader.conf && {entries} && echo ok",
                equals="ok",
            )
        )
    if sel.firmware == "uefi":
        proof.append(
            _probe(
                f"ESP at /boot is vfat and at least the resolver-recommended {esp} MiB",
                "python3 -c \"import os; s=os.statvfs('/boot'); "
                f"print('ok' if s.f_blocks*s.f_frsize >= {esp}*1024*1024 else 'small')\"",
                equals="ok",
            )
        )
    if sel.encryption == "luks":
        proof.append(
            _probe(
                "Root storage is LUKS with a crypttab entry (LUKS/openswap contract preserved)",
                "lsblk -o FSTYPE -rn | grep -q crypto_LUKS && grep -q . /etc/crypttab && echo ok",
                equals="ok",
            )
        )
    else:
        proof.append(
            _probe(
                "No LUKS container on the installed storage",
                "lsblk -o FSTYPE -rn | grep -q crypto_LUKS && echo luks || echo none",
                equals="none",
            )
        )
    if sel.bluetooth:
        proof.append(
            _probe(
                "Bluetooth capability on: bluez stack installed and bluetooth.service enabled",
                "pacman -Qq bluez bluez-utils >/dev/null && systemctl is-enabled bluetooth.service",
                equals="enabled",
            )
        )
        proof.append(
            _probe(
                "Bluetooth doctor (Bluetooth workstream contract) reports the service ok",
                "horneroctl hardware bluetooth doctor --json | python3 -c "
                "\"import json,sys;print(json.load(sys.stdin)['data']['bluetooth-service'])\"",
                equals="ok",
            )
        )
    else:
        proof.append(
            _probe(
                "Bluetooth capability off: bluez stack absent and bluetooth.service not enabled",
                "pacman -Qq bluez bluez-utils >/dev/null 2>&1 && echo present || echo absent",
                equals="absent",
            )
        )
    if sel.edition == "studio":
        ids = list(sel.specializations)
        proof.append(
            _probe(
                "Studio specializations persisted in the installed profile",
                "python3 -c \"import pathlib; d=pathlib.Path('/usr/lib/hornero/system-profile.json')"
                f'.read_text(); print(all(s in d for s in {ids!r}))"',
                equals="True",
            )
        )
        apps = (
            "ardour kdenlive obs-studio blender"
            if sel.specializations == STUDIO_COMPLETE
            else "ardour kdenlive"
        )
        proof.append(
            _probe(
                "Representative packages of the selected Studio specializations are installed",
                f"pacman -Qq {apps} >/dev/null && echo present || echo absent",
                equals="present",
            )
        )
        proof.append(
            _probe(
                "Proprietary REAPER was not installed by group selection",
                "pacman -Qq reaper >/dev/null 2>&1 && echo present || echo absent",
                equals="absent",
            )
        )
    if sel.edition == "gaming":
        proof.append(
            _probe(
                "Gaming platform tools from the canonical composition are installed",
                "pacman -Qq gamescope gamemode mangohud >/dev/null && echo present || echo absent",
                equals="present",
            )
        )
        proof.append(
            _probe(
                "Steam was not installed by group selection (explicit opt-in only)",
                "pacman -Qq steam >/dev/null 2>&1 && echo present || echo absent",
                equals="absent",
            )
        )
    proof.append({"note": "Desktop frame (non-blank) for the record", "screenshot": "installed-desktop"})
    return {
        "id": f"install-pairwise/{sel.slug}",
        "purpose": (
            f"NOT RUN until a candidate ISO exists. A {sel.edition} installation "
            f"(kernels {', '.join(kernels)}; primary {sel.primary_kernel}; {sel.bootloader} on "
            f"{sel.firmware}; encryption {sel.encryption}; bluetooth {bt}) from the candidate ISO, "
            "rebooted into the installed system, matches the canonical resolved choice: kernel and "
            "initramfs images, boot entries, ESP size, LUKS state, edition composition and capability "
            "services. This never qualifies physical hardware."
        ),
        "covers": ["installer#11", "qa#19"],
        "requires": {
            "firmware": sel.firmware,
            "bootloader": sel.bootloader,
            "kernels": kernels,
            "primaryKernel": sel.primary_kernel,
            "encryption": sel.encryption,
            "edition": sel.edition,
            "specializations": list(sel.specializations),
            "capabilities": {"bluetooth": sel.bluetooth},
            "isoRequired": True,
        },
        "instruction": (
            f"Using the existing VM harness (~/.local/share/hornero/install-test/run-install-vm.sh "
            f"<name> {sel.firmware} 40 iso), boot the candidate ISO in a disposable VM, launch the "
            f"graphical installer, choose edition {sel.edition}"
            + (f" with specializations {', '.join(sel.specializations)}" if sel.specializations else "")
            + f", kernels {', '.join(kernels)} (primary {sel.primary_kernel}), bootloader "
            f"{sel.bootloader}, encryption {sel.encryption}, bluetooth {bt}; create the QA user, let "
            "installation finish, reboot with the ISO detached (run-install-vm.sh <name> "
            f"{sel.firmware} 40 noiso), unlock LUKS if prompted and authenticate at the greeter."
            f"{fallback_note} Then reboot once more into the installed system and leave the "
            "installed desktop running for the proofs."
        ),
        "proof": proof,
        "media": ["installed-desktop"],
        "budget": {"wall_s": 3600},
        "artifacts": {"screenshots": "always", "logs": "always"},
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    expected = {}
    for sel in pairwise_rows():
        doc = render(sel)
        expected[f"{sel.slug}.yaml"] = yaml.safe_dump(doc, sort_keys=False, allow_unicode=False)
    for stale in OUT.glob("*.yaml"):
        if stale.name not in expected:
            stale.unlink()
    for name, text in sorted(expected.items()):
        (OUT / name).write_text(text, encoding="utf-8")
    print(f"wrote {len(expected)} scenarios to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
