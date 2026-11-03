"""Pin the VM-safe connectivity/bluetooth scenarios.

All three scenarios run against the default QEMU topology (no
adapter). The doctor shipped in v0.2.0-preview30 and passed on installed Desktop/Studio VMs with honest no-adapter results (Preview 30 release checklist, HorneroOS/hornero); the probe scenarios here are still scheduled for the next approved KVM QA window and no hardware PASS is claimed.
These tests pin only their honesty contract.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from hornero_qa.scenario import load

ROOT = Path(__file__).parent.parent / "scenarios" / "connectivity"
IDS = ["bluetooth-no-adapter", "bluetooth-service-down", "bluetooth-power-toggle"]
MUTATING_PROOF = re.compile(r"pacman|systemctl (start|restart|enable)|\brm\b|>\s*/")


def _proofs(name: str) -> list[dict[str, Any]]:
    return load(ROOT / f"{name}.yaml").proof


def test_scenario_identities() -> None:
    for name in IDS:
        sc = load(ROOT / f"{name}.yaml")
        assert sc.id == f"connectivity/{name}"
        assert sc.wall_s == 60


def test_scenarios_only_use_bluetooth_doctor_probes() -> None:
    for name in IDS:
        for proof in _proofs(name):
            run = str(proof["probe"]["run"])
            assert "horneroctl hardware bluetooth doctor --json" in run
            assert not MUTATING_PROOF.search(run), run


def test_no_adapter_scenario_distinguishes_service_from_hardware() -> None:
    runs = [str(p["probe"]["run"]) for p in _proofs("bluetooth-no-adapter")]
    assert any("['adapter']" in run for run in runs)
    assert any("['bluetooth-service']" in run for run in runs)


def test_service_down_scenario_stops_service_only_in_setup() -> None:
    sc = load(ROOT / "bluetooth-service-down.yaml")
    assert sc.setup["commands"] == ["systemctl stop bluetooth.service"]


def test_scenarios_never_claim_hardware_qualification() -> None:
    for name in IDS:
        sc = load(ROOT / f"{name}.yaml")
        assert "never qualifies physical hardware" in sc.purpose or "NOT TESTED" in sc.purpose
