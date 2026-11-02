"""Pin the VM-safe gpu-driver-coherence scenario (HorneroOS/hornero#342).

The check is not yet in the pinned doctor contract fixture
(``tests/fixtures/gaming-doctor-contract.json``, preview35), so the
guest scenario is NOT TESTED on a VM yet: it will fail its first
proof until a horneroctl tag ships ``gpu-driver-coherence``. These
tests only pin the scenario's honesty contract — read-only probes,
ok/fail values, no hardware qualification — never hardware evidence.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from hornero_qa.scenario import load

SCENARIO = Path(__file__).parent.parent / "scenarios" / "gaming" / "gpu-driver-coherence.yaml"

# Anything that would install, load, remove or reconfigure a driver
# (or the system) instead of only reporting coherence.
MUTATING = re.compile(
    r"pacman|yay|paru|modprobe|insmod|rmmod|systemctl|mkinitcpio"
    r"|\binstall\b|\brm\b|\bmv\b|\btee\b|>\s*/"
)


def _proofs() -> list[dict[str, Any]]:
    return load(SCENARIO).proof


def _runs() -> list[str]:
    return [str(proof["probe"]["run"]) for proof in _proofs()]


def test_scenario_identity_and_coverage() -> None:
    sc = load(SCENARIO)
    assert sc.id == "gaming/gpu-driver-coherence"
    assert "hornero#342" in sc.covers
    assert sc.wall_s == 60
    assert len(sc.proof) == 5


def test_scenario_expects_the_doctor_coherence_check() -> None:
    runs = _runs()
    assert any("'gpu-driver-coherence' in" in run for run in runs)
    assert all("horneroctl gaming doctor" in run for run in runs)


def test_scenario_probes_are_read_only() -> None:
    for run in _runs():
        assert not MUTATING.search(run), run


def test_scenario_never_promises_hardware_qualification() -> None:
    sc = load(SCENARIO)
    assert "never qualifies physical hardware" in sc.purpose
    assert any("qualif" in str(proof.get("note", "")) for proof in sc.proof)
    for forbidden in ("compatible", "fps", "performance"):
        assert not any(forbidden in run for run in _runs()), forbidden
