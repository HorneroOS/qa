"""Contract tests for the Playground acceptance scenarios (HorneroOS/playground#1)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

from hornero_qa.cli import main
from hornero_qa.display_profiles import OFFICIAL_DEFAULT_PROFILE
from hornero_qa.scenario import load

REPO_ROOT = Path(__file__).resolve().parent.parent
PLAYGROUND_DIR = REPO_ROOT / "scenarios" / "playground"
TRIAGE_PATH = REPO_ROOT / "docs" / "scenario-triage.yaml"

EXPECTED_IDS = (
    "playground/apps-and-welcome",
    "playground/presenter-dnd",
    "playground/vm-boot-ready",
)


def test_playground_scenarios_conform_to_schema_and_reuse_native_engine() -> None:
    files = sorted(PLAYGROUND_DIR.glob("*.yaml"))
    assert [f"playground/{p.stem}" for p in files] == list(EXPECTED_IDS)

    for path in files:
        sc = load(path)
        assert sc.id == f"playground/{path.stem}"
        assert "playground#1" in sc.covers
        assert sc.requires.get("engine") == "native"
        assert sc.requires.get("compositor") == "hyprland"
        assert sc.requires.get("outputs") == 1
        assert sc.requires.get("resolution") == OFFICIAL_DEFAULT_PROFILE.resolution
        assert sc.resolution == (1920, 1080)
        assert sc.proof

        cmds = list(sc.setup.get("commands") or []) + [
            str(item["probe"]["run"]) for item in sc.steps + sc.proof if "probe" in item
        ]
        for cmd in cmds:
            assert "qemu-system-" not in cmd
            checked = subprocess.run(["bash", "-n"], input=cmd, text=True, capture_output=True, check=False)
            assert checked.returncode == 0, f"shell syntax error in {sc.id}: {cmd!r}: {checked.stderr}"


def test_playground_scenarios_cover_expected_contracts() -> None:
    boot = load(PLAYGROUND_DIR / "vm-boot-ready.yaml")
    boot_cmds = " ".join(str(p["probe"]["run"]) for p in boot.proof if "probe" in p)
    assert "Hyprland" in boot_cmds
    assert "welcome status" in boot_cmds
    assert "hyprctl configerrors" in boot_cmds

    apps = load(PLAYGROUND_DIR / "apps-and-welcome.yaml")
    apps_cmds = " ".join(str(p["probe"]["run"]) for p in apps.proof if "probe" in p)
    assert "horneroctl --json store list" in apps_cmds
    assert "horneroctl --json welcome status" in apps_cmds

    dnd = load(PLAYGROUND_DIR / "presenter-dnd.yaml")
    dnd_cmds = " ".join(str(p["probe"]["run"]) for p in dnd.steps + dnd.proof if "probe" in p)
    assert "qs ipc call notifs enableDnd" in dnd_cmds
    assert "qs ipc call notifs isDndEnabled" in dnd_cmds
    assert "qs ipc call notifs disableDnd" in dnd_cmds


def test_playground_triage_does_not_claim_unearned_pass() -> None:
    triage = yaml.safe_load(TRIAGE_PATH.read_text(encoding="utf-8"))
    entries = triage["scenarios"]
    for sid in EXPECTED_IDS:
        assert sid in entries
        entry = entries[sid]
        assert entry["decision"] == "fix"
        assert "NOT RUN" in entry["rationale"]
        assert "no PASS is claimed" in entry["rationale"]


def test_cli_list_includes_playground_suite(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["list"]) == 0
    out = capsys.readouterr().out
    for sid in EXPECTED_IDS:
        assert sid in out
