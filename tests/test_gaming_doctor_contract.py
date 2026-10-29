"""Pin the horneroctl gaming doctor JSON contract (gate: gaming-doctor-contract).

The doctor reports capability and registration only. This test pins the
command name and check-name set from the canonical implementation and
fails if compatibility/performance-style claims ever enter the contract.
The fixture is evidence-derived, not aspirational: see its ``source``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FIXTURE = Path(__file__).parent / "fixtures" / "gaming-doctor-contract.json"

FORBIDDEN_CLAIM_KEYS = {
    "compatible",
    "compatibility",
    "fps",
    "performance",
    "qualified",
    "supported_games",
}


def _contract() -> dict[str, Any]:
    value: Any = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_doctor_command_name() -> None:
    assert _contract()["command"] == "gaming doctor"


def test_doctor_check_names_cover_required_capabilities() -> None:
    keys = set(_contract()["data_keys"])
    required = {
        "gaming-selection",
        "vulkan-icd",
        "vulkan-32bit-loader",
        "steam",
        "gamemode",
        "gamescope",
        "mangohud",
        "pipewire",
        "wireplumber",
        "xdg-desktop-portal",
        "controllers",
        "recovery-readiness",
    }
    assert required <= keys


def test_doctor_values_are_ok_or_fail_only() -> None:
    assert set(_contract()["data_values"]) == {"ok", "fail"}


def test_doctor_contract_makes_no_compatibility_or_performance_claims() -> None:
    keys = {key.lower() for key in _contract()["data_keys"]}
    assert keys.isdisjoint(FORBIDDEN_CLAIM_KEYS)
