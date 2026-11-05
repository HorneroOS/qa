#!/usr/bin/env python3
"""Scripted QMP installer drives for offline Preview 33 qualification.

These flows encode the exact Calamares click/type sequences that were
executed and visually verified by hand during the Preview 33 goals
(1280x800 framebuffer fractions). They are deliberately dumb: timed
steps plus a screenshot at every stage. The verdict oracle is the
scenario's own proof probes, typed into the installed system with
`PROBE<n>:` markers and archived as screenshots for operator review
before `hornero-qa import` records an explicit verdict — this driver
never claims PASS by itself.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from hornero_qa.qmp import QMP
from hornero_qa.scenario import load, resolve

_SHIFT = {
    "!": "1", "@": "2", "#": "3", "$": "4", "%": "5", "^": "6", "&": "7",
    "*": "8", "(": "9", ")": "0", "_": "minus", "+": "equal", "{": "bracket_left",
    "}": "bracket_right", "|": "backslash", ":": "semicolon", '"': "apostrophe",
    "<": "comma", ">": "dot", "?": "slash", "~": "grave_accent",
}  # fmt: skip
_PLAIN = {
    " ": "spc", "\n": "ret", "\t": "tab", "-": "minus", "=": "equal",
    "[": "bracket_left", "]": "bracket_right", "\\": "backslash",
    ";": "semicolon", "'": "apostrophe", ",": "comma", ".": "dot",
    "/": "slash", "`": "grave_accent",
}  # fmt: skip

TEST_PASSWORD = "hornero-test-2026"  # VM-only fixture credential, as before
LUKS_PASSPHRASE = "hornero-test-2026"

# Edition-chooser rows (fractions at 1280x800), pitch measured on the
# preview32 chooser; the post-click screenshot is archived for review.
EDITION_ROWS = {
    "desktop-hyprland": 0.057,
    "desktop-niri": 0.076,
    "studio-hyprland": 0.095,
    "studio-niri": 0.114,
    "gaming-hyprland": 0.133,
    "gaming-niri": 0.152,
}


class Driver:
    def __init__(self, qmp: QMP, evidence: Path) -> None:
        self.q = qmp
        self.ev = evidence
        self.ev.mkdir(parents=True, exist_ok=True)
        self.seq = 0

    def shot(self, name: str) -> Path:
        self.seq += 1
        path = self.ev / f"{self.seq:02d}-{name}.png"
        self.q.screendump(path)
        return path

    def click(self, x: float, y: float, wait_s: float = 2.0) -> None:
        self.q.pointer_abs(x, y)
        time.sleep(0.15)
        self.q.click()
        time.sleep(wait_s)

    def key(self, chord: str, wait_s: float = 1.0) -> None:
        self.q.chord(chord.split("-"))
        time.sleep(wait_s)

    def type(self, text: str, wait_s: float = 0.5) -> None:
        for ch in text:
            if ch.isupper():
                self.q.chord(["shift", ch.lower()])
            elif ch in _SHIFT:
                self.q.chord(["shift", _SHIFT[ch]])
            elif ch in _PLAIN:
                self.q.chord([_PLAIN[ch]])
            else:
                self.q.chord([ch])
            time.sleep(0.01)
        time.sleep(wait_s)

    def run_typed(self, command: str, wait_s: float = 3.0) -> None:
        self.type(command)
        self.key("ret", wait_s=wait_s)


@dataclass(frozen=True)
class Cell:
    name: str
    scenario: str
    firmware: str  # uefi | bios
    encrypted: bool
    edition_row: str


CELLS: dict[str, Cell] = {
    "desktop-uefi": Cell(
        "desktop-uefi", "install/desktop-uefi-unencrypted", "uefi", False, "desktop-hyprland"
    ),
    "studio-uefi": Cell("studio-uefi", "install/studio-uefi-unencrypted", "uefi", False, "studio-hyprland"),
    "gaming-uefi": Cell("gaming-uefi", "install/gaming-uefi-unencrypted", "uefi", False, "gaming-hyprland"),
    "desktop-bios-luks": Cell(
        "desktop-bios-luks", "install/desktop-bios-encrypted", "bios", True, "desktop-hyprland"
    ),
    "studio-uefi-luks": Cell(
        "studio-uefi-luks", "install/studio-uefi-encrypted", "uefi", True, "studio-hyprland"
    ),
}


def drive_install(d: Driver, cell: Cell, *, install_timeout_s: int = 1800) -> None:
    """Live boot -> Calamares install -> Done. Caller reboots without ISO."""
    time.sleep(75)
    d.shot("boot")
    d.click(0.949, 0.077)  # close Hornero Welcome
    d.click(0.864, 0.941, wait_s=3)  # Welcome -> Location
    d.click(0.864, 0.941, wait_s=3)  # Location -> Keyboard
    d.click(0.864, 0.941, wait_s=6)  # Keyboard -> Partitions
    d.click(0.298, 0.108, wait_s=4)  # Erase disk
    d.shot("partitions")
    if cell.encrypted:
        # Encrypt system is pre-checked on this ISO; fill both fields.
        d.click(0.403, 0.722, wait_s=0.5)
        d.type(LUKS_PASSPHRASE)
        d.click(0.621, 0.722, wait_s=0.5)
        d.type(LUKS_PASSPHRASE, wait_s=2)
    else:
        d.click(0.215, 0.686, wait_s=3)  # uncheck Encrypt system
    d.shot("partition-choice")
    d.click(0.864, 0.941, wait_s=3)  # -> Users
    d.click(0.288, 0.095, wait_s=0.5)
    for value in ("Hornero Test", "hornero", "hornero-test", TEST_PASSWORD, TEST_PASSWORD):
        d.type(value)
        d.key("tab")
    d.shot("users")
    d.click(0.864, 0.941, wait_s=4)  # -> Edition and compositor
    d.click(0.285, EDITION_ROWS[cell.edition_row], wait_s=3)
    d.shot("edition")
    d.click(0.864, 0.941, wait_s=5)  # -> Summary
    d.shot("summary")
    d.click(0.864, 0.941, wait_s=5)  # Install
    d.click(0.602, 0.536, wait_s=10)  # Install Now (destructive confirm)
    deadline = time.time() + install_timeout_s
    while time.time() < deadline:
        time.sleep(60)
        d.shot("installing")
        # Completion is not detectable blind; the loop simply gives the
        # installer generous time. The post-reboot probes are the oracle.
        if time.time() > deadline - 60:
            break
    d.shot("install-final-state")
    d.click(0.940, 0.941, wait_s=3)  # Done (no-op if still installing)


def drive_first_boot_probes(d: Driver, cell: Cell) -> list[str]:
    """After reboot without ISO: unlock (if LUKS), log in, run scenario probes."""
    time.sleep(45)
    d.shot("installed-boot")
    if cell.encrypted:
        d.type(LUKS_PASSPHRASE)
        d.key("ret", wait_s=45)
        d.shot("after-unlock")
    d.click(0.5, 0.5, wait_s=3)  # reveal greeter form
    d.type(TEST_PASSWORD)
    d.key("ret", wait_s=35)
    d.shot("installed-desktop")
    d.key("meta_l-ret", wait_s=4)  # terminal
    scenario = load(resolve(cell.scenario))
    typed: list[str] = []
    for index, step in enumerate(scenario.proof, start=1):
        probe = step.get("probe") or {}
        command = probe.get("run")
        if command:
            d.run_typed(f"echo PROBE{index}:; {command}", wait_s=4)
            typed.append(command)
            d.shot(f"probe-{index}")
    d.run_typed("echo PARITY:; horneroctl version; pacman -Q | wc -l", wait_s=4)
    d.shot("parity")
    return typed
