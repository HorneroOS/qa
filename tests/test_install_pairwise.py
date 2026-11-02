"""Unit/contract tests for the pairwise install acceptance design.

These run now, without an ISO. The scenario declarations they pin are
NOT RUN until a candidate ISO exists (see docs/INSTALL-PAIRWISE.md).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from hornero_qa.install_matrix import (
    STUDIO_COMBINED,
    STUDIO_COMPLETE,
    Selection,
    all_valid_selections,
    esp_recommended_mib,
    mandatory_rows,
    pairwise_rows,
    uncovered_pairs,
    validate_selection,
)
from hornero_qa.scenario import load

ROOT = Path(__file__).parent.parent
PAIRWISE = ROOT / "scenarios" / "install-pairwise"
NEGATIVE = ROOT / "scenarios" / "install-pairwise-negative"


def test_pairwise_coverage_is_complete_and_deterministic() -> None:
    rows = pairwise_rows()
    assert uncovered_pairs(rows) == set()
    assert pairwise_rows() == rows


def test_no_unbootable_combination_is_generated() -> None:
    for sel in all_valid_selections():
        validate_selection(sel)
        assert not (sel.bootloader == "systemd-boot" and sel.firmware == "bios")


def test_systemd_boot_bios_is_refused_with_actionable_message() -> None:
    with pytest.raises(ValueError, match="systemd-boot needs UEFI"):
        validate_selection(Selection("linux", "systemd-boot", "bios", "none", "desktop", True))


def test_specializations_only_on_studio() -> None:
    with pytest.raises(ValueError, match="not available for desktop"):
        validate_selection(Selection("linux", "grub", "uefi", "none", "desktop", True, STUDIO_COMBINED))


def test_mandatory_rows_are_included() -> None:
    rows = pairwise_rows()
    for sel in mandatory_rows():
        assert sel in rows


def test_esp_sizing_matches_design_contract() -> None:
    def sel(kernels: str, bootloader: str) -> Selection:
        return Selection(kernels, bootloader, "uefi", "none", "desktop", True)

    assert esp_recommended_mib(sel("linux", "grub")) == 512
    assert esp_recommended_mib(sel("dual-primary-linux", "grub")) == 768
    assert esp_recommended_mib(sel("linux", "systemd-boot")) == 1024
    assert esp_recommended_mib(sel("dual-primary-linux", "systemd-boot")) == 1280


def _generated_text() -> dict[str, str]:
    import importlib.util

    spec = importlib.util.spec_from_file_location("gen", ROOT / "scripts" / "generate-install-pairwise.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {
        f"{sel.slug}.yaml": yaml.safe_dump(module.render(sel), sort_keys=False) for sel in pairwise_rows()
    }


def test_generated_scenarios_do_not_drift() -> None:
    expected = _generated_text()
    on_disk = {p.name: p.read_text(encoding="utf-8") for p in PAIRWISE.glob("*.yaml")}
    assert on_disk == expected


def test_scenario_requires_match_their_selection() -> None:
    by_slug = {sel.slug: sel for sel in pairwise_rows()}
    assert len(by_slug) == len(pairwise_rows()), "scenario slugs must be unique"
    for path in sorted(PAIRWISE.glob("*.yaml")):
        sc = load(path)
        sel = by_slug[path.stem]
        assert sc.id == f"install-pairwise/{sel.slug}"
        assert sc.requires["kernels"] == list(sel.kernel_packages)
        assert sc.requires["primaryKernel"] == sel.primary_kernel
        assert sc.requires["primaryKernel"] in sc.requires["kernels"]
        assert sc.requires["bootloader"] == sel.bootloader
        assert sc.requires["firmware"] == sel.firmware
        assert sc.requires["encryption"] == sel.encryption
        assert sc.requires["edition"] == sel.edition
        assert sc.requires["capabilities"] == {"bluetooth": sel.bluetooth}
        assert sc.requires["isoRequired"] is True
        assert "NOT RUN" in sc.purpose


def test_bluetooth_toggle_reuses_bluetooth_workstream_names() -> None:
    on = [load(p) for p in PAIRWISE.glob("*.yaml") if load(p).requires["capabilities"]["bluetooth"]]
    off = [load(p) for p in PAIRWISE.glob("*.yaml") if not load(p).requires["capabilities"]["bluetooth"]]
    assert on and off
    for sc in on:
        runs = " ".join(str(p.get("probe", {}).get("run", "")) for p in sc.proof)
        assert "bluez bluez-utils" in runs
        assert "bluetooth.service" in runs
        assert "horneroctl hardware bluetooth doctor --json" in runs
    for sc in off:
        runs = " ".join(str(p.get("probe", {}).get("run", "")) for p in sc.proof)
        assert "bluez bluez-utils" in runs and "absent" in runs


def test_combined_studio_specializations_are_covered() -> None:
    studio = [s for s in pairwise_rows() if s.edition == "studio"]
    assert any(s.specializations == STUDIO_COMBINED for s in studio)
    assert any(s.specializations == STUDIO_COMPLETE for s in studio)


def test_dual_kernel_lts_fallback_row_exists() -> None:
    assert any(s.kernels == "dual-primary-lts" for s in mandatory_rows())


def test_negative_scenarios_are_declared_not_run() -> None:
    ids = {load(p).id for p in NEGATIVE.glob("*.yaml")}
    assert ids == {
        "install-pairwise-negative/systemd-boot-bios-not-offered",
        "install-pairwise-negative/cancel-during-install",
        "install-pairwise-negative/wrong-luks-passphrase",
    }
    for path in NEGATIVE.glob("*.yaml"):
        assert "NOT RUN" in load(path).purpose


def test_existing_install_scenarios_retained() -> None:
    ids = {load(p).id for p in (ROOT / "scenarios" / "install").glob("*.yaml")}
    assert len(ids) == 9
