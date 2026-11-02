"""Hardware-free Bluetooth acceptance contracts (design T1/T2/T4).

These pin catalogue, service, BlueZ, WirePlumber and power-persistence
expectations as data. They run without Bluetooth hardware and without
sibling repos; they do not claim the product ships any of it yet.
Physical pairing, audio and suspend behaviour stays NOT TESTED.
"""

from __future__ import annotations

import configparser
import json
import re
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).parent / "fixtures"
ACCEPTANCE = FIXTURES / "bluetooth-acceptance.json"


def _acceptance() -> dict[str, Any]:
    value: Any = json.loads(ACCEPTANCE.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _main_conf() -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(FIXTURES / "bluetooth" / "main.conf", encoding="utf-8")
    return parser


def test_acceptance_fixture_is_honestly_not_tested() -> None:
    assert _acceptance()["status"] == "not-tested"


def test_catalogue_package_presence_contract() -> None:
    catalogue = _acceptance()["catalogue"]
    assert catalogue["packages_required_desktop"] == ["bluez", "bluez-utils"]
    # The shell replaces Blueman; it must not return via the catalogue.
    assert "blueman" in catalogue["packages_forbidden"]
    assert set(catalogue["packages_forbidden"]).isdisjoint(catalogue["packages_required_desktop"])
    assert set(catalogue["editions_inheriting_desktop"]) == {"desktop", "studio", "gaming"}
    for package in catalogue["packages_required_desktop"]:
        assert catalogue["provenance_licenses"][package] == ["GPL-2.0-or-later"]


def test_service_enablement_is_non_mandatory() -> None:
    service = _acceptance()["service_enablement"]
    assert service["unit"] == "bluetooth.service"
    assert service["installer_action"] == "enable"
    # A mandatory unit would fail installs on Bluetooth-less machines.
    assert service["installer_mandatory"] is False
    assert service["systemd_preset"] == "enable bluetooth.service"


def test_bluez_config_assertions() -> None:
    parser = _main_conf()
    assert parser["General"]["controllermode"] == "dual"
    assert parser["General"]["justworksrepairing"] == "never"
    assert parser["General"]["fastconnectable"] == "false"


def test_power_persistence_config_never_disables_autoenable() -> None:
    parser = _main_conf()
    # AutoEnable=false is the known wound: BlueZ never persists Powered.
    assert parser["Policy"]["autoenable"] == "true"
    raw = (FIXTURES / "bluetooth" / "main.conf").read_text(encoding="utf-8")
    assert not re.search(r"^\s*AutoEnable\s*=\s*false", raw, re.MULTILINE)
    power = _acceptance()["power_persistence"]
    assert power["mechanism"] == "rfkill"
    assert power["persisted_by"] == "systemd-rfkill.service"
    assert power["main_conf_autoenable"] is True
    assert "AutoEnable=false" in power["forbidden"]


def test_wireplumber_policy_assertions() -> None:
    text = (FIXTURES / "bluetooth" / "51-hornero-bluetooth.conf").read_text(encoding="utf-8")
    codecs = re.search(r"bluez5\.codecs\s*=\s*\[([^\]]+)\]", text)
    assert codecs is not None
    # Codec preference order is part of the contract, not just membership.
    assert codecs.group(1).split() == ["ldac", "aptx_hd", "aptx", "sbc_xq", "aac", "sbc"]
    assert "bluetooth.autoswitch-to-headset-profile = true" in text
    assert "bluez5.enable-msbc = true" in text
    # No global autosuspend disable anywhere in the shipped policy.
    assert "autosuspend" not in text.lower()


def test_security_invariants_are_not_weakened() -> None:
    invariants = _acceptance()["security_invariants"]
    assert invariants["just_works_repairing"] == "never"
    assert invariants["auto_accept_pairing"] is False
    assert invariants["permanent_discoverability"] is False
    assert invariants["discoverable_timeout_s"] == 120
    assert invariants["passwordless_polkit"] is False
    assert invariants["global_usb_autosuspend_disable"] is False
    assert invariants["polling"] is False
