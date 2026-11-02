"""Pairwise/combinatorial install acceptance design.

The canonical catalogue lives in HorneroOS/hornero; this module only
declares QA factor levels and constraints. It contains no edition
package lists: package-composition probes in the generated scenarios
derive from the installed system profile and the kernel, bootloader
and capability IDs declared here.

Never offer an unbootable combination: systemd-boot requires UEFI,
the primary kernel must be installed, and at least one kernel is
required. LUKS (luks1, unencrypted ESP at /boot, openswap behaviour)
is orthogonal to the bootloader except for that firmware rule.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

KERNELS: dict[str, tuple[str, ...]] = {
    "linux": ("linux",),
    "linux-lts": ("linux-lts",),
    "dual-primary-linux": ("linux", "linux-lts"),
    "dual-primary-lts": ("linux-lts", "linux"),
}
BOOTLOADERS = ("grub", "systemd-boot")
FIRMWARES = ("uefi", "bios")
ENCRYPTIONS = ("none", "luks")
EDITIONS = ("desktop", "studio", "gaming")
# Combined Studio specializations: two curated groups selected together.
STUDIO_COMBINED = ("audio-music-production", "video-editing-post-production")
STUDIO_COMPLETE = ("complete-creative-workstation",)

# ESP sizing from the design contract: base per bootloader plus a
# per-additional-kernel allowance (vmlinuz + initramfs + fallback).
_ESP_BASE_MIB = {"grub": 512, "systemd-boot": 1024}
_ESP_PER_EXTRA_KERNEL_MIB = 256


@dataclass(frozen=True)
class Selection:
    kernels: str  # key into KERNELS
    bootloader: str
    firmware: str
    encryption: str
    edition: str
    bluetooth: bool
    specializations: tuple[str, ...] = field(default=())

    @property
    def kernel_packages(self) -> tuple[str, ...]:
        return KERNELS[self.kernels]

    @property
    def primary_kernel(self) -> str:
        return KERNELS[self.kernels][0]

    @property
    def slug(self) -> str:
        bt = "bt-on" if self.bluetooth else "bt-off"
        slug = f"{self.edition}-{self.kernels}-{self.bootloader}-{self.firmware}-{self.encryption}-{bt}"
        if self.specializations == STUDIO_COMPLETE:
            slug += "-studio-complete"
        return slug


def esp_recommended_mib(sel: Selection) -> int:
    return _ESP_BASE_MIB[sel.bootloader] + _ESP_PER_EXTRA_KERNEL_MIB * (len(sel.kernel_packages) - 1)


def validate_selection(sel: Selection) -> None:
    """Raise ValueError with an actionable message for unbootable picks."""
    if sel.kernels not in KERNELS:
        raise ValueError(f"unknown kernel selection {sel.kernels!r}; choose one of {sorted(KERNELS)}")
    if not sel.kernel_packages:
        raise ValueError("Select at least one kernel.")
    if sel.bootloader not in BOOTLOADERS:
        raise ValueError(f"unknown bootloader {sel.bootloader!r}; choose one of {list(BOOTLOADERS)}")
    if sel.firmware not in FIRMWARES:
        raise ValueError(f"unknown firmware {sel.firmware!r}; choose one of {list(FIRMWARES)}")
    if sel.bootloader == "systemd-boot" and sel.firmware == "bios":
        raise ValueError(
            "systemd-boot needs UEFI — this machine booted in legacy BIOS mode. "
            "Choose GRUB or reboot the installer in UEFI mode."
        )
    if sel.encryption not in ENCRYPTIONS:
        raise ValueError(f"unknown encryption {sel.encryption!r}; choose one of {list(ENCRYPTIONS)}")
    if sel.edition not in EDITIONS:
        raise ValueError(f"unknown edition {sel.edition!r}; choose one of {list(EDITIONS)}")
    if sel.specializations and sel.edition != "studio":
        raise ValueError(f"specializations are not available for {sel.edition} — deselect them.")


def _specializations_for(edition: str) -> tuple[str, ...]:
    return STUDIO_COMBINED if edition == "studio" else ()


def all_valid_selections() -> list[Selection]:
    out: list[Selection] = []
    for kernels, bootloader, firmware, encryption, edition, bluetooth in itertools.product(
        KERNELS, BOOTLOADERS, FIRMWARES, ENCRYPTIONS, EDITIONS, (True, False)
    ):
        sel = Selection(
            kernels, bootloader, firmware, encryption, edition, bluetooth, _specializations_for(edition)
        )
        try:
            validate_selection(sel)
        except ValueError:
            continue
        out.append(sel)
    return out


def _pairs(sel: Selection) -> set[tuple[tuple[str, object], tuple[str, object]]]:
    factors: list[tuple[str, object]] = [
        ("kernels", sel.kernels),
        ("bootloader", sel.bootloader),
        ("firmware", sel.firmware),
        ("encryption", sel.encryption),
        ("edition", sel.edition),
        ("bluetooth", sel.bluetooth),
    ]
    return set(itertools.combinations(sorted(factors, key=lambda f: f[0]), 2))


def uncovered_pairs(rows: list[Selection]) -> set[tuple[tuple[str, object], tuple[str, object]]]:
    valid = all_valid_selections()
    required: set[tuple[tuple[str, object], tuple[str, object]]] = set()
    for sel in valid:
        required |= _pairs(sel)
    covered: set[tuple[tuple[str, object], tuple[str, object]]] = set()
    for sel in rows:
        covered |= _pairs(sel)
    return required - covered


def mandatory_rows() -> list[Selection]:
    """Critical rows required on every candidate ISO, pairwise or not."""
    rows = [
        # Default path, both encryption states.
        Selection("linux", "grub", "uefi", "luks", "desktop", True),
        Selection("linux", "grub", "uefi", "none", "desktop", True),
        # Every valid bootloader x firmware pair with LUKS.
        Selection("linux", "grub", "bios", "luks", "desktop", True),
        Selection("linux", "systemd-boot", "uefi", "luks", "desktop", True),
        # Gaming candidate rows from the design contract.
        Selection("linux", "grub", "uefi", "luks", "gaming", True),
        Selection("linux", "grub", "bios", "none", "gaming", False),
        # Dual-kernel row booted via the LTS fallback entry.
        Selection("dual-primary-lts", "grub", "uefi", "luks", "desktop", True),
        # Combined Studio specializations (union group).
        Selection("linux", "grub", "uefi", "luks", "studio", True, STUDIO_COMPLETE),
    ]
    for sel in rows:
        validate_selection(sel)
    return rows


def pairwise_rows() -> list[Selection]:
    """Deterministic greedy pairwise covering array plus mandatory rows."""
    candidates = all_valid_selections()
    remaining = uncovered_pairs([])
    rows: list[Selection] = []
    while remaining:
        best = max(
            candidates,
            key=lambda sel: (len(_pairs(sel) & remaining), sel.slug),
        )
        gained = _pairs(best) & remaining
        if not gained:
            break
        rows.append(best)
        remaining -= gained
    for sel in mandatory_rows():
        if sel not in rows:
            rows.append(sel)
    return rows
