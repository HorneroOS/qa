from __future__ import annotations

from pathlib import Path

import pytest

from hornero_qa.gaming_gate import evaluate
from hornero_qa.studio_gate import StudioGateError

ROOT = Path(__file__).parent.parent
MANIFEST = ROOT / "docs" / "gaming-acceptance.yaml"


def test_gaming_gate_is_blocked_and_never_promotes(tmp_path: Path) -> None:
    report = evaluate(MANIFEST, tmp_path)
    assert report["schema"] == "hornero.qa.gaming-acceptance/1"
    assert report["eligible_for_owner_review"] is False
    assert report["recommendation"] == "blocked"
    assert "Gaming Preview recommendation blocked" in report["summary"]
    assert report["summary"].startswith("Gaming Preview recommendation blocked: 9")
    assert all(item["blocking_reasons"] for item in report["items"] if item["id"] != "vrr-hdr-experimental")


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
