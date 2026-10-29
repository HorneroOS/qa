from __future__ import annotations

from pathlib import Path

import pytest

from hornero_qa.gaming_gate import evaluate
from hornero_qa.studio_gate import StudioGateError

ROOT = Path(__file__).parent.parent
MANIFEST = ROOT / "docs" / "gaming-acceptance.yaml"


def test_gaming_gate_is_blocked_and_never_promotes() -> None:
    report = evaluate(MANIFEST, ROOT / "docs/evidence/runs")
    assert report["schema"] == "hornero.qa.gaming-acceptance/1"
    assert report["eligible_for_owner_review"] is False
    assert report["recommendation"] == "blocked"
    assert "Gaming Preview recommendation blocked" in report["summary"]
    assert report["summary"].startswith("Gaming Preview recommendation blocked: 6")
    accepted = {"clean-install-first-boot", "gaming-doctor-contract", "anti-cheat-honesty"}
    assert all(
        item["blocking_reasons"]
        for item in report["items"]
        if item["id"] not in accepted | {"vrr-hdr-experimental"}
    )
    for item_id in accepted:
        item = next(i for i in report["items"] if i["id"] == item_id)
        assert item["status"] == "accepted" and item["blocking_reasons"] == []


def test_gaming_gate_rejects_studio_schema(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        MANIFEST.read_text(encoding="utf-8").replace(
            "hornero.qa.gaming-acceptance/1", "hornero.qa.studio-acceptance/1"
        ),
        encoding="utf-8",
    )
    with pytest.raises(StudioGateError):
        evaluate(bad, tmp_path)


def test_gaming_gate_rejects_manifest_missing_mandatory_item(tmp_path: Path) -> None:
    import yaml

    doc = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    doc["items"] = [i for i in doc["items"] if i["id"] != "steam-proton-gameplay"]
    bad = tmp_path / "gaming-acceptance.yaml"
    bad.write_text(yaml.safe_dump(doc), encoding="utf-8")
    with pytest.raises(StudioGateError, match="mandatory gate item"):
        evaluate(bad, tmp_path)


def test_gaming_gate_rejects_demoted_mandatory_item(tmp_path: Path) -> None:
    import yaml

    doc = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    for item in doc["items"]:
        if item["id"] == "gaming-doctor-contract":
            item["required"] = False
    bad = tmp_path / "gaming-acceptance.yaml"
    bad.write_text(yaml.safe_dump(doc), encoding="utf-8")
    with pytest.raises(StudioGateError, match="must stay required"):
        evaluate(bad, tmp_path)
