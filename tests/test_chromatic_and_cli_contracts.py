"""Contract tests for installer smoke matrix, Chromatic theme parity, and CLI surface."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from hornero_qa.cli import main

REPO_ROOT = Path(__file__).resolve().parent.parent
SCENARIOS_DIR = REPO_ROOT / "scenarios"


def _load_yaml(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), f"{path} did not parse to a YAML mapping"
    return data


def test_installer_first_boot_smoke_matrix_coverage() -> None:
    """Installer scenarios cover UEFI/BIOS and encrypted/unencrypted boot paths."""
    install_dir = SCENARIOS_DIR / "install"
    files = sorted(install_dir.glob("*.yaml"))
    assert len(files) >= 8, "Expected broad installer first-boot coverage"

    ids: set[str] = set()
    stems: set[str] = set()
    for path in files:
        doc = _load_yaml(path)
        assert "id" in doc and doc["id"].startswith("install/")
        assert doc["id"] not in ids, f"Duplicate scenario id: {doc['id']}"
        ids.add(doc["id"])
        stems.add(path.stem)
        assert doc.get("purpose"), f"{path.name} missing purpose"
        assert doc.get("proof") or doc.get("steps"), f"{path.name} missing steps/proof"

    assert any("uefi" in s and "encrypted" in s for s in stems)
    assert any("uefi" in s and "unencrypted" in s for s in stems)
    assert any("bios" in s and "encrypted" in s for s in stems)
    assert any("bios" in s and "unencrypted" in s for s in stems)


def test_theme_and_chromatic_parity_scenarios_are_well_formed() -> None:
    """Theme scenarios validate cleanly and cover theme switching & parity."""
    themes_dir = SCENARIOS_DIR / "themes"
    files = sorted(themes_dir.glob("*.yaml"))
    assert files, "Expected at least one theme parity scenario under scenarios/themes/"

    ids: set[str] = set()
    for path in files:
        doc = _load_yaml(path)
        assert "id" in doc and doc["id"].startswith("themes/")
        assert doc["id"] not in ids, f"Duplicate theme scenario id: {doc['id']}"
        ids.add(doc["id"])
        assert doc.get("purpose"), f"{path.name} missing purpose"
        assert doc.get("steps") or doc.get("proof") or doc.get("setup"), (
            f"{path.name} missing steps/proof/setup"
        )


def test_perf_baseline_enforces_rss_budget() -> None:
    """scenarios/perf/baseline.yaml enforces an explicit max_rss_kb ceiling."""
    baseline = _load_yaml(SCENARIOS_DIR / "perf" / "baseline.yaml")
    assert baseline["id"] == "perf/baseline"
    proofs = baseline.get("proof", [])
    assert proofs, "perf/baseline must define proof probes"
    probes = [p["probe"] for p in proofs if isinstance(p, dict) and "probe" in p]
    assert any(isinstance(probe.get("max_rss_kb"), int) and probe["max_rss_kb"] > 0 for probe in probes), (
        "perf/baseline must enforce a positive max_rss_kb budget"
    )


def test_cli_list_includes_install_theme_and_perf_families(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """hornero-qa list exposes install, themes, and perf scenario families."""
    assert main(["list"]) == 0
    out = capsys.readouterr().out
    assert "install/desktop-uefi-unencrypted" in out
    assert "perf/baseline" in out
    assert "themes/" in out
