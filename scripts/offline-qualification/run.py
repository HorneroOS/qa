#!/usr/bin/env python3
"""Offline Preview 33 qualification runner (maintainer-executed).

Runs WITHOUT Muse: the maintainer closes Muse (freeing its
~5 GiB RSS), then runs this script from a normal terminal. It enforces
the resource preflight from preflight.py before every VM, executes the
selected install cells sequentially against one exact ISO through the
existing manual QMP harness conventions, preserves all evidence under
the state directory, and checkpoints progress in manifest.json so a
stopped run resumes without repeating completed expensive phases.

This runner never records PASS by itself: cells end as `executed`
(with screenshots and RESULT.draft.md), and an operator later imports
them with explicit verdicts via `hornero-qa import` — the same
evidence contract as every other tracked bundle.

Usage (see docs/OFFLINE-QUALIFICATION.md):
  run.py --iso /path/to/candidate.iso [--cells a,b,c] [--resume]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from drive import (
    CELLS,
    ENCRYPT_SYSTEM_CHECKBOX,
    TEST_PASSWORD,
    Cell,
    Driver,
    drive_first_boot_probes,
    drive_install,
)
from preflight import assert_floor, live_check

from hornero_qa.qmp import QMP

VM_MIB = 4096  # Calamares enforces a 4 GiB guest minimum; never lower it.
VM_CPUS = 4
DISK_GIB = 60
BASE = Path.home() / ".local/share/hornero/install-test"
# installer#94 (disable-cancel-during-exec), merged 2026-11-05.
MITIGATION_REVISION = "cf72bbc764dc5940f179c13b8a9e915a9511e2e1"


def run_config() -> dict[str, int]:
    """Execution configuration that must stay identical across --resume."""
    return {"vm_mib": VM_MIB, "vm_cpus": VM_CPUS, "disk_gib": DISK_GIB}


def attempt_vm_name(cell_name: str, attempt: int) -> str:
    return f"p33off-{cell_name}-a{attempt}"


def sidecar_installer_revision(iso_path: Path) -> str | None:
    """installerRevision recorded by the build next to the ISO, if any."""
    sidecar = iso_path.with_name(iso_path.name + ".manifest.json")
    if not sidecar.is_file():
        return None
    try:
        data: dict = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    revision = data.get("installerRevision")
    return revision if isinstance(revision, str) and revision else None


def cancel_mitigation_proven(iso_path: Path, installer_repo: Path | None) -> tuple[bool, str]:
    """Artifact-level proof that the ISO contains installer#94.

    Provenance comes from the build-generated sidecar manifest's
    installerRevision — never from the ISO filename. The revision must
    be the mitigation commit itself or a descendant of it; ancestry is
    verified against an installer checkout when one is provided.
    """
    revision = sidecar_installer_revision(iso_path)
    if revision is None:
        return False, "no sidecar manifest with installerRevision next to the ISO"
    if revision == MITIGATION_REVISION:
        return True, f"sidecar installerRevision is the mitigation commit {revision[:12]}"
    if installer_repo is None:
        return False, (
            f"sidecar installerRevision {revision[:12]} is not the mitigation commit and "
            "no --installer-repo checkout was provided to verify ancestry"
        )
    probe = subprocess.run(
        ["git", "-C", str(installer_repo), "merge-base", "--is-ancestor", MITIGATION_REVISION, revision],
        capture_output=True,
        timeout=30,
    )
    if probe.returncode == 0:
        return True, f"sidecar installerRevision {revision[:12]} descends from the mitigation commit"
    if probe.returncode == 1:
        return False, f"sidecar installerRevision {revision[:12]} does NOT contain the mitigation commit"
    return False, "git ancestry check failed (unknown revision or not an installer checkout)"


def final_exit_code(manifest: Manifest, selected: list[str]) -> int:
    """0 only when every selected cell reached `executed`."""
    for name in selected:
        if manifest.data["cells"].get(name, {}).get("status") != "executed":
            return 1
    return 0


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Manifest:
    def __init__(self, state_dir: Path) -> None:
        self.dir = state_dir
        self.path = state_dir / "manifest.json"
        if self.path.exists():
            self.data: dict = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self.data = {
                "run_id": state_dir.name,
                "created": now(),
                "iso": None,
                "cells": {},
                "notes": [],
            }
            self.save()

    def save(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2) + "\n", encoding="utf-8")

    def cell(self, name: str) -> dict:
        return self.data["cells"].setdefault(name, {"status": "pending"})


def launch_vm(name: str, firmware: str, *, with_iso: bool, iso_path: Path, fresh_disk: bool = False) -> None:
    """Launch one harness-faithful VM (same devices/DNS as run-install-vm.sh).

    `fresh_disk=True` (every new install attempt) recreates the qcow2 and
    UEFI vars from scratch: a partially installed disk is never silently
    reused for a retry. The previous attempt's evidence is preserved by
    the caller under its own attempt directory.
    """
    disk = BASE / f"{name}.qcow2"
    sock = BASE / f"{name}.qmp"
    if fresh_disk:
        disk.unlink(missing_ok=True)
        (BASE / f"{name}-vars.fd").unlink(missing_ok=True)
    if not disk.exists():
        subprocess.run(["qemu-img", "create", "-q", "-f", "qcow2", str(disk), f"{DISK_GIB}G"], check=True)
    sock.unlink(missing_ok=True)
    fwargs = ""
    if firmware == "uefi":
        vars_fd = BASE / f"{name}-vars.fd"
        if not vars_fd.exists():
            shutil.copy("/usr/share/OVMF/x64/OVMF_VARS.4m.fd", vars_fd)
        fwargs = (
            "-drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/x64/OVMF_CODE.4m.fd "
            f"-drive if=pflash,format=raw,file={vars_fd}"
        )
    cdargs = ""
    boot = "order=d,menu=on"
    if with_iso:
        cdargs = (
            f"-drive file={iso_path},format=raw,if=none,id=cd0,readonly=on "
            "-device ide-cd,drive=cd0,bootindex=0"
        )
        boot = "order=c"
    (BASE / "fake-resolv.conf").write_text("nameserver 1.1.1.1\nnameserver 8.8.8.8\n", encoding="utf-8")
    inner = (
        f"mount --bind '{BASE}/fake-resolv.conf' /etc/resolv.conf && exec qemu-system-x86_64 "
        f"-enable-kvm -cpu host -machine q35 -smp {VM_CPUS} -m {VM_MIB} -name hornero-install-{name} "
        f"-pidfile {BASE}/{name}.pid "
        f"{fwargs} -device virtio-vga,xres=1280,yres=800 "
        f"-drive file={disk},format=qcow2,if=virtio {cdargs} -boot {boot} "
        "-netdev user,id=net0,hostfwd=tcp:127.0.0.1:2230-:22 -device virtio-net-pci,netdev=net0,id=nic0 "
        f"-display none -serial file:{BASE}/{name}-serial.log -qmp unix:{sock},server,nowait "
        "-usb -device qemu-xhci -device usb-tablet -device usb-kbd"
    )
    with (BASE / f"{name}-qemu.log").open("ab") as log:
        subprocess.Popen(
            ["setsid", "-f", "unshare", "-rm", "sh", "-c", inner],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
        )
    QMP.wait(sock, deadline_s=30).sock.close()


def preflight_or_exit(state_dir: Path, label: str) -> None:
    result = live_check(vm_mib=VM_MIB, state_root=state_dir)
    print(f"[preflight:{label}]")
    for message in result.messages:
        print(f"  {message}")
    if not result.ok:
        print("preflight failed; nothing was launched. Fix the diagnostics above and re-run with --resume.")
        raise SystemExit(3)


def write_result_draft(
    cell: Cell, evidence: Path, iso_name: str, iso_sha: str, typed_probes: list[str]
) -> None:
    shots = sorted(p.name for p in evidence.glob("*.png"))
    lines = [
        f"# {cell.name} — offline qualification run (DRAFT, verdict pending operator review)",
        "",
        f"Scenario: `{cell.scenario}`",
        f"ISO: `{iso_name}`",
        f"SHA-256: `{iso_sha}`",
        f"Executed: {now()} by scripts/offline-qualification/run.py (scripted QMP drive, timed phases).",
        "",
        "## Scenario probes typed on the installed system",
        "",
    ]
    lines += [f"- `{cmd}`" for cmd in typed_probes] or ["- (none recorded)"]
    lines += ["", "## Screenshots (in order)", ""] + [f"- {s}" for s in shots]
    lines += [
        "",
        "## Verdict",
        "",
        "PENDING OPERATOR REVIEW — inspect the probe screenshots, then import with an",
        "explicit verdict via `hornero-qa import` (never infer PASS from this draft).",
        "",
    ]
    (evidence / "RESULT.draft.md").write_text("\n".join(lines), encoding="utf-8")


def run_cell(manifest: Manifest, cell: Cell, iso_path: Path, iso_sha: str) -> None:
    record = manifest.cell(cell.name)
    if record.get("status") == "executed":
        print(f"[cell:{cell.name}] already executed — checkpoint respected, skipping")
        return
    attempt = int(record.get("attempts", 0)) + 1
    vm_name = attempt_vm_name(cell.name, attempt)
    evidence = manifest.dir / "evidence" / cell.name / f"attempt-{attempt}"
    evidence.mkdir(parents=True, exist_ok=True)
    history: list = record.setdefault("history", [])
    history.append({"attempt": attempt, "started": now(), "vm": vm_name, "disk": f"{vm_name}.qcow2"})
    record.update(status="running", started=now(), vm=vm_name, scenario=cell.scenario, attempts=attempt)
    manifest.save()
    sock = BASE / f"{vm_name}.qmp"
    typed: list[str] = []
    try:
        preflight_or_exit(manifest.dir, f"{cell.name}:install")
        launch_vm(vm_name, cell.firmware, with_iso=True, iso_path=iso_path, fresh_disk=True)
        q = QMP.wait(sock, deadline_s=30)
        drive_install(Driver(q, evidence), cell)
        q.quit()
        time.sleep(3)
        assert_floor(f"cell {cell.name} first boot")
        preflight_or_exit(manifest.dir, f"{cell.name}:first-boot")
        launch_vm(vm_name, cell.firmware, with_iso=False, iso_path=iso_path)
        q = QMP.wait(sock, deadline_s=30)
        d = Driver(q, evidence)
        typed = drive_first_boot_probes(d, cell)
        d.run_typed(f"echo {TEST_PASSWORD} | sudo -S poweroff", wait_s=10)
        time.sleep(5)
        record.update(status="executed", finished=now(), probes_typed=len(typed))
    except SystemExit:
        record.update(status="preflight-blocked", finished=now())
        manifest.save()
        raise
    except Exception as exc:  # evidence preserved; manifest records the failure
        record.update(status="failed", finished=now(), error=f"{type(exc).__name__}: {exc}")
    finally:
        if history:
            history[-1].update(status=record.get("status"), finished=now())
        write_result_draft(cell, evidence, iso_path.name, iso_sha, typed)
        manifest.save()
        print(f"[cell:{cell.name}] attempt {attempt} -> {record.get('status')}")


def run_cancel_contract(manifest: Manifest, iso_path: Path, iso_sha: str) -> None:
    """installer#93 proof: disabled Cancel on Install step + view-step cancel run."""
    from drive import EDITION_ROWS

    name = "cancel-contract"
    record = manifest.cell(name)
    if record.get("status") == "executed":
        print(f"[cell:{name}] already executed — skipping")
        return
    attempt = int(record.get("attempts", 0)) + 1
    evidence = manifest.dir / "evidence" / name / f"attempt-{attempt}"
    evidence.mkdir(parents=True, exist_ok=True)
    record.setdefault("history", []).append({"attempt": attempt, "started": now()})
    record.update(
        status="running",
        started=now(),
        scenario="install-pairwise-negative/cancel-during-install",
        attempts=attempt,
    )
    manifest.save()
    cell = Cell(name, "install-pairwise-negative/cancel-during-install", "uefi", False, "desktop-hyprland")
    try:
        # (1) Install-step screenshot: after Install Now, Cancel must be disabled.
        preflight_or_exit(manifest.dir, "cancel:install-step")
        vm = f"p33off-cancel-a{attempt}"
        launch_vm(vm, "uefi", with_iso=True, iso_path=iso_path, fresh_disk=True)
        q = QMP.wait(BASE / f"{vm}.qmp", deadline_s=30)
        d = Driver(q, evidence)
        time.sleep(75)
        d.shot("cancel-live-boot")
        d.click(0.949, 0.077)
        d.click(0.864, 0.941, wait_s=3)
        d.click(0.864, 0.941, wait_s=3)
        d.click(0.864, 0.941, wait_s=6)
        d.click(0.298, 0.108, wait_s=4)
        d.click(*ENCRYPT_SYSTEM_CHECKBOX, wait_s=3)  # uncheck Encrypt system
        d.click(0.864, 0.941, wait_s=3)
        d.click(0.288, 0.095, wait_s=0.5)
        for value in ("Hornero Test", "hornero", "hornero-test", TEST_PASSWORD, TEST_PASSWORD):
            d.type(value)
            d.key("tab")
        d.click(0.864, 0.941, wait_s=4)
        d.click(0.285, EDITION_ROWS["desktop-hyprland"], wait_s=3)
        d.click(0.864, 0.941, wait_s=5)
        d.shot("cancel-summary-cancel-enabled")
        d.click(0.864, 0.941, wait_s=5)
        d.click(0.602, 0.536, wait_s=20)  # Install Now; reach packages job
        d.shot("cancel-install-step-disabled")
        q.quit()
        time.sleep(3)
        # (2) View-step cancel on a fresh disk: Summary -> Cancel -> confirm quit.
        preflight_or_exit(manifest.dir, "cancel:view-step")
        vm = f"p33off-cancel-b{attempt}"
        launch_vm(vm, "uefi", with_iso=True, iso_path=iso_path, fresh_disk=True)
        q = QMP.wait(BASE / f"{vm}.qmp", deadline_s=30)
        d = Driver(q, evidence)
        time.sleep(75)
        d.click(0.949, 0.077)
        d.click(0.864, 0.941, wait_s=3)
        d.click(0.864, 0.941, wait_s=3)
        d.click(0.864, 0.941, wait_s=6)
        d.shot("viewstep-before-cancel")
        d.click(0.794, 0.941, wait_s=3)  # Cancel (enabled on view steps)
        d.shot("viewstep-quit-dialog")
        d.key("ret", wait_s=3)  # confirm quit (default action)
        d.shot("viewstep-after-quit")
        q.quit()
        record.update(status="executed", finished=now())
    except SystemExit:
        record.update(status="preflight-blocked", finished=now())
        manifest.save()
        raise
    except Exception as exc:
        record.update(status="failed", finished=now(), error=f"{type(exc).__name__}: {exc}")
    finally:
        write_result_draft(cell, evidence, iso_path.name, iso_sha, [])
        manifest.save()
        print(f"[cell:{name}] -> {record.get('status')}")


def run_failure_cleanup(manifest: Manifest, iso_path: Path, iso_sha: str) -> None:
    """Package-failure cleanup: cut the NIC mid-transaction, then probe cleanup.

    Failure injection uses QMP human-monitor `set_link nic0 off` during the
    packages job. Calamares should surface the failure; the live-terminal
    probes afterwards check for leftover mounts/swap/processes. Best-effort
    and opt-in (not in the default cell list) because failure timing is
    inherently less deterministic than the happy paths.
    """
    from drive import EDITION_ROWS

    name = "failure-cleanup"
    record = manifest.cell(name)
    if record.get("status") == "executed":
        print(f"[cell:{name}] already executed — skipping")
        return
    attempt = int(record.get("attempts", 0)) + 1
    evidence = manifest.dir / "evidence" / name / f"attempt-{attempt}"
    evidence.mkdir(parents=True, exist_ok=True)
    record.setdefault("history", []).append({"attempt": attempt, "started": now()})
    record.update(
        status="running",
        started=now(),
        scenario="(offline-only; no tracked scenario yet)",
        attempts=attempt,
    )
    manifest.save()
    cell = Cell(name, "offline/failure-cleanup", "uefi", False, "desktop-hyprland")
    try:
        preflight_or_exit(manifest.dir, "failure-cleanup")
        vm = attempt_vm_name(name, attempt)
        launch_vm(vm, "uefi", with_iso=True, iso_path=iso_path, fresh_disk=True)
        q = QMP.wait(BASE / f"{vm}.qmp", deadline_s=30)
        d = Driver(q, evidence)
        time.sleep(75)
        d.click(0.949, 0.077)
        d.click(0.864, 0.941, wait_s=3)
        d.click(0.864, 0.941, wait_s=3)
        d.click(0.864, 0.941, wait_s=6)
        d.click(0.298, 0.108, wait_s=4)
        d.click(*ENCRYPT_SYSTEM_CHECKBOX, wait_s=3)  # uncheck Encrypt system
        d.click(0.864, 0.941, wait_s=3)
        d.click(0.288, 0.095, wait_s=0.5)
        for value in ("Hornero Test", "hornero", "hornero-test", TEST_PASSWORD, TEST_PASSWORD):
            d.type(value)
            d.key("tab")
        d.click(0.864, 0.941, wait_s=4)
        d.click(0.285, EDITION_ROWS["desktop-hyprland"], wait_s=3)
        d.click(0.864, 0.941, wait_s=5)
        d.click(0.864, 0.941, wait_s=5)
        d.click(0.602, 0.536, wait_s=90)  # Install Now; let downloads begin
        d.shot("failure-before-nic-off")
        q.cmd("human-monitor-command", **{"command-line": "set_link nic0 off"})
        d.shot("failure-nic-off")
        time.sleep(240)  # pacman retries/timeouts; Calamares should fail the job
        d.shot("failure-after-timeout")
        d.key("ret", wait_s=3)  # dismiss a possible error dialog default action
        d.key("meta_l-ret", wait_s=4)
        d.run_typed("echo CLEAN1:; mount | grep -E 'calamares|target' ; echo done", wait_s=4)
        d.run_typed("echo CLEAN2:; swapon --show; echo done", wait_s=4)
        d.run_typed("echo CLEAN3:; pgrep -a -x calamares; pgrep -a -x pacman; echo done", wait_s=4)
        d.shot("failure-cleanup-probes")
        q.quit()
        record.update(status="executed", finished=now())
    except SystemExit:
        record.update(status="preflight-blocked", finished=now())
        manifest.save()
        raise
    except Exception as exc:
        record.update(status="failed", finished=now(), error=f"{type(exc).__name__}: {exc}")
    finally:
        write_result_draft(cell, evidence, iso_path.name, iso_sha, [])
        manifest.save()
        print(f"[cell:{name}] -> {record.get('status')}")


def write_summary(manifest: Manifest) -> None:
    lines = [
        f"# Offline qualification run {manifest.data['run_id']}",
        "",
        f"ISO: {manifest.data.get('iso')}",
        "",
        "| Cell | Scenario | Status | Started | Finished |",
        "|---|---|---|---|---|",
    ]
    for name, rec in sorted(manifest.data["cells"].items()):
        lines.append(
            f"| {name} | {rec.get('scenario', '-')} | {rec.get('status')} "
            f"| {rec.get('started', '-')} | {rec.get('finished', '-')} |"
        )
    lines += [
        "",
        "Statuses are execution states, not verdicts. Review each evidence directory",
        "(`RESULT.draft.md` + screenshots) and import with explicit verdicts via",
        "`hornero-qa import`. `executed` never implies PASS.",
        "",
    ]
    (manifest.dir / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iso", required=True, type=Path, help="exact candidate/signed ISO to test")
    parser.add_argument(
        "--cells",
        default=",".join([*CELLS, "cancel-contract"]),
        help=f"comma list from {sorted([*CELLS, 'cancel-contract'])}",
    )
    parser.add_argument("--state-dir", type=Path, default=None)
    parser.add_argument("--resume", action="store_true", help="respect checkpoints in manifest.json")
    parser.add_argument(
        "--installer-repo",
        type=Path,
        default=None,
        help="installer checkout used to verify cancel-contract ancestry (or $INSTALLER_REPO)",
    )
    parser.add_argument(
        "--expected-sha256",
        default=None,
        help="refuse to pin or resume unless the ISO hashes to this SHA-256",
    )
    args = parser.parse_args(argv)

    iso_path = args.iso.resolve()
    if not iso_path.is_file():
        print(f"ISO not found: {iso_path}")
        return 2
    state_dir = args.state_dir or (
        Path.home() / "hornero-p33-offline" / datetime.now(UTC).strftime("run-%Y%m%dT%H%M%SZ")
    )
    state_dir.mkdir(parents=True, exist_ok=True)
    manifest = Manifest(state_dir)
    if not args.resume and manifest.data["cells"]:
        print("state dir already has cell records; use --resume or a fresh --state-dir")
        return 2
    print(f"hashing ISO (one pass)… state={state_dir}")
    iso_sha = sha256_of(iso_path)
    if args.expected_sha256 and iso_sha.lower() != args.expected_sha256.lower():
        print(f"refusing ISO: expected sha256 {args.expected_sha256}, but --iso hashes to {iso_sha}")
        return 2
    # The ISO identity and execution config are immutable within a run:
    # --resume must never mix checkpoints/evidence from different ISOs.
    existing = manifest.data.get("iso")
    if existing:
        if not args.resume:
            print("state dir already pins an ISO; use --resume or a fresh --state-dir")
            return 2
        if existing.get("sha256") != iso_sha:
            print(
                f"refusing --resume: state dir pins ISO sha256 {existing.get('sha256')}, "
                f"but --iso hashes to {iso_sha}. Use a fresh --state-dir for a different ISO."
            )
            return 2
        if manifest.data.get("config") != run_config():
            print(
                f"refusing --resume: execution config changed "
                f"({manifest.data.get('config')} -> {run_config()}); use a fresh --state-dir."
            )
            return 2
    else:
        manifest.data["iso"] = {"path": str(iso_path), "name": iso_path.name, "sha256": iso_sha}
        manifest.data["config"] = run_config()
        sidecar = iso_path.with_name(iso_path.name + ".manifest.json")
        if sidecar.is_file():
            manifest.data["iso"]["sidecar_manifest"] = json.loads(sidecar.read_text(encoding="utf-8"))
        manifest.save()
    print(f"ISO {iso_path.name} sha256={iso_sha}")

    selected = [c.strip() for c in args.cells.split(",") if c.strip()]
    special = {"cancel-contract", "failure-cleanup"}
    unknown = [c for c in selected if c not in CELLS and c not in special]
    if unknown:
        print(f"unknown cells: {unknown}")
        return 2
    if "cancel-contract" in selected:
        installer_repo = args.installer_repo or (
            Path(os.environ["INSTALLER_REPO"]) if os.environ.get("INSTALLER_REPO") else None
        )
        proven, reason = cancel_mitigation_proven(iso_path, installer_repo)
        record = manifest.cell("cancel-contract")
        if record.get("status") == "executed":
            print("[cancel-gate] already executed in this run — checkpoint respected")
        elif proven:
            record["mitigation_provenance"] = reason
            manifest.save()
            print(f"[cancel-gate] applicable: {reason}")
        else:
            record.update(status="not-applicable", finished=now(), gate_reason=reason)
            manifest.save()
            write_summary(manifest)
            print(
                f"[cancel-gate] cancel-contract NOT applicable to this artifact: {reason}. "
                "It is recorded as not-applicable (not executed, not PASS). "
                "Other cells can still run by selecting them explicitly without cancel-contract."
            )
            selected.remove("cancel-contract")
            if not selected:
                return 1
    for name in selected:
        if name == "cancel-contract":
            run_cancel_contract(manifest, iso_path, iso_sha)
        elif name == "failure-cleanup":
            run_failure_cleanup(manifest, iso_path, iso_sha)
        else:
            run_cell(manifest, CELLS[name], iso_path, iso_sha)
        write_summary(manifest)
    write_summary(manifest)
    print(f"done. summary: {state_dir / 'SUMMARY.md'}")
    print(
        "next: review evidence, then import verdicts with hornero-qa import "
        "(see docs/OFFLINE-QUALIFICATION.md)."
    )
    code = final_exit_code(manifest, selected)
    gated = manifest.data["cells"].get("cancel-contract", {}).get("status") == "not-applicable"
    if code != 0 or gated:
        print("one or more selected cells did not reach `executed`; exiting nonzero (evidence preserved).")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
