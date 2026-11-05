"""Offline qualification runner contracts (no VMs are launched).

Covers the resource preflight gates, manifest checkpoints, cell map
integrity, and the failure behavior that must never silently bypass the
RAM/disk/serialization rules.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts" / "offline-qualification"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


preflight = _load("preflight")
drive = _load("drive")
run = _load("run")

MEMINFO_OK = "MemTotal:       16000000 kB\nMemAvailable:   11000000 kB\n"
MEMINFO_LOW = "MemTotal:       16000000 kB\nMemAvailable:    6000000 kB\n"
VMSTAT_QUIET = (
    "procs ---swap---\n r b si so bi bo\n 1 0 0 0 5 5 0 0 0 0 0 0 0 0 0 0\n 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0\n"
)
# vmstat columns: r b swpd free buff cache si so ...
VMSTAT_QUIET = " 1 0 100 200 300 400 0 0 1 2 3 4 5 6 7 8\n 0 0 100 200 300 400 0 0 0 0 0 0 0 0 0 0\n"
VMSTAT_SWAPPING = " 1 0 100 200 300 400 0 0 1 2 3 4 5 6 7 8\n 0 0 100 200 300 400 12 3 0 0 0 0 0 0 0 0\n"
PS_CLEAN = "python3 run.py\nbash\n"
PS_QEMU = "qemu-system-x86_64 -m 4096 -name hornero-install-x\n"


def test_preflight_passes_with_headroom() -> None:
    result = preflight.check_resources(
        vm_mib=4096, meminfo_text=MEMINFO_OK, vmstat_text=VMSTAT_QUIET, ps_text=PS_CLEAN, disk_free_gib=100.0
    )
    assert result.ok, result.messages


def test_preflight_refuses_below_required_ram() -> None:
    result = preflight.check_resources(
        vm_mib=4096, meminfo_text=MEMINFO_LOW, vmstat_text=VMSTAT_QUIET, ps_text=PS_CLEAN, disk_free_gib=100.0
    )
    assert not result.ok
    assert any("MemAvailable" in m for m in result.messages)


def test_preflight_scales_requirement_with_vm_size() -> None:
    # 11 GiB available passes a 4 GiB VM (needs 8) but not an 8 GiB VM (needs 12).
    small = preflight.check_resources(
        vm_mib=4096, meminfo_text=MEMINFO_OK, vmstat_text=VMSTAT_QUIET, ps_text=PS_CLEAN, disk_free_gib=100.0
    )
    large = preflight.check_resources(
        vm_mib=8192, meminfo_text=MEMINFO_OK, vmstat_text=VMSTAT_QUIET, ps_text=PS_CLEAN, disk_free_gib=100.0
    )
    assert small.ok and not large.ok


def test_preflight_refuses_swap_activity_and_competing_vm_and_low_disk() -> None:
    result = preflight.check_resources(
        vm_mib=4096, meminfo_text=MEMINFO_OK, vmstat_text=VMSTAT_SWAPPING, ps_text=PS_QEMU, disk_free_gib=5.0
    )
    assert not result.ok
    joined = " | ".join(result.messages)
    assert "swap activity" in joined
    assert "another heavy job" in joined
    assert "disk free" in joined


def test_competing_process_scan_ignores_grep_lines() -> None:
    assert preflight.find_competing_processes("grep qemu-system\n") == []


def test_cells_map_to_registered_scenarios_and_rows() -> None:
    from hornero_qa.scenario import load, resolve

    for cell in drive.CELLS.values():
        scenario = load(resolve(cell.scenario))
        assert scenario.proof, f"{cell.name}: scenario has no probes to type"
        assert cell.edition_row in drive.EDITION_ROWS
        assert cell.firmware in {"uefi", "bios"}


def test_manifest_checkpoint_roundtrip(tmp_path: Path) -> None:
    manifest = run.Manifest(tmp_path)
    manifest.cell("desktop-uefi").update(status="executed")
    manifest.save()
    reloaded = run.Manifest(tmp_path)
    assert reloaded.data["cells"]["desktop-uefi"]["status"] == "executed"
    on_disk = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert on_disk["run_id"] == tmp_path.name


def test_runner_refuses_dirty_state_without_resume(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    iso = tmp_path / "fake.iso"
    iso.write_bytes(b"x")
    manifest = run.Manifest(tmp_path / "state")
    manifest.cell("desktop-uefi").update(status="executed")
    manifest.save()
    code = run.main(["--iso", str(iso), "--state-dir", str(tmp_path / "state")])
    assert code == 2
    assert "--resume" in capsys.readouterr().out


def test_runner_refuses_unknown_cells(tmp_path: Path) -> None:
    iso = tmp_path / "fake.iso"
    iso.write_bytes(b"x")
    assert run.main(["--iso", str(iso), "--state-dir", str(tmp_path / "s"), "--cells", "nope"]) == 2


def test_result_draft_never_claims_pass(tmp_path: Path) -> None:
    cell = drive.CELLS["desktop-uefi"]
    run.write_result_draft(cell, tmp_path, "x.iso", "abc", ["echo hi"])
    text = (tmp_path / "RESULT.draft.md").read_text(encoding="utf-8")
    assert "PENDING OPERATOR REVIEW" in text
    assert "PASS" not in text.replace("never infer PASS", "")
