"""Pin the horneroctl bluetooth doctor JSON contract (design T6).

The doctor shipped in v0.2.0-preview30 and passed on installed Desktop/Studio VMs with honest no-adapter results (Preview 30 release checklist, HorneroOS/hornero); the probe scenarios here are still scheduled for the next approved KVM QA window and no hardware PASS is claimed. The fixtures
pin the expected shape (adapter / no-adapter / rfkill-blocked) so the
shipped doctor keeps being checked against them, never the reverse.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FIXTURE = Path(__file__).parent / "fixtures" / "bluetooth-doctor-contract.json"
FORBIDDEN_CLAIM_KEYS = {"compatible", "paired", "connected", "qualified", "audio-quality"}


def _contract() -> dict[str, Any]:
    value: Any = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_fixture_is_honestly_not_tested() -> None:
    contract = _contract()
    assert contract["status"] == "not-tested"
    assert "NOT" in contract["source"]


def test_doctor_command_name() -> None:
    assert _contract()["command"] == "hardware bluetooth doctor"
    assert _contract()["invocation"] == "horneroctl hardware bluetooth doctor --json"


def test_doctor_values_are_ok_or_fail_only() -> None:
    assert set(_contract()["data_values"]) == {"ok", "fail"}


def test_all_states_cover_same_check_names() -> None:
    contract = _contract()
    required = set(contract["data_keys"])
    assert {"adapter", "bluetooth-service", "rfkill", "powered", "wireplumber-bluez"} <= required
    for state in contract["states"].values():
        assert set(state["data"]) == required
        assert set(state["data"].values()) <= {"ok", "fail"}


def test_adapter_state_is_fully_ok() -> None:
    state = _contract()["states"]["adapter"]
    assert state["exit"] == 0
    assert set(state["data"].values()) == {"ok"}


def test_no_adapter_state_fails_adapter_not_service() -> None:
    state = _contract()["states"]["no-adapter"]
    assert state["exit"] == 1
    assert state["data"]["adapter"] == "fail"
    assert state["data"]["powered"] == "fail"
    # Service and tools may be healthy without hardware; never conflated.
    assert state["data"]["bluetooth-service"] == "ok"
    assert state["data"]["bluez-tools"] == "ok"
    assert state["data"]["rfkill"] == "ok"


def test_rfkill_blocked_state_is_distinct_from_no_adapter() -> None:
    contract = _contract()
    blocked = contract["states"]["rfkill-blocked"]
    assert blocked["exit"] == 1
    assert blocked["data"]["adapter"] == "ok"
    assert blocked["data"]["rfkill"] == "fail"
    assert blocked["data"]["powered"] == "fail"
    assert blocked["data"] != contract["states"]["no-adapter"]["data"]


def test_contract_makes_no_pairing_or_audio_claims() -> None:
    keys = {key.lower() for key in _contract()["data_keys"]}
    assert keys.isdisjoint(FORBIDDEN_CLAIM_KEYS)
