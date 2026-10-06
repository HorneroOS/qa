from __future__ import annotations

import json
from pathlib import Path

from hornero_qa.evidence import Bundle, load_bundle
from hornero_qa.report import write_report
from tests.conftest import SavePng, desktop


def test_bundle_roundtrip(tmp_path: Path, save_png: SavePng) -> None:
    meta = {"scenario": "smoke/x", "product": {"shell_sha": "abc"}, "environment": {"engine": "native"}}
    b = Bundle.create(tmp_path / "runs", "r1", meta, "id: smoke/x\n")
    b.action("key", value="super+d")
    b.assertion({"kind": "probe", "ok": True, "where": "proof 0", "detail": "ok"})
    shot = b.screenshot(save_png(desktop(), "f.png"), "desktop")
    b.finish({"verdict": "pass", "class": None})

    side = json.loads(shot.with_suffix(".json").read_text())
    assert side["schema"] == "hornero.qa.screenshot/1"
    assert side["product"] == {"shell_sha": "abc"} and side["run_id"] == "r1"
    assert len(side["sha256"]) == 64
    assert side["environment"]["captured_resolution"] == "320x200"

    loaded = load_bundle(b.root)
    assert loaded["run"]["schema"] == "hornero.qa.run/1"
    assert loaded["result"]["verdict"] == "pass"
    assert loaded["actions"][0]["kind"] == "key"
    assert loaded["screenshots"] == ["001-desktop.png"]

    html = write_report(b.root).read_text()
    assert "PASS" in html and "001-desktop.png" in html and "<script" not in html


def test_report_escapes(tmp_path: Path) -> None:
    b = Bundle.create(tmp_path, "r2", {"scenario": "<x>", "instruction": "<script>alert(1)</script>"}, "")
    b.finish({"verdict": "fail", "reason": "<img onerror=1>"})
    html = write_report(b.root).read_text()
    assert "<script>alert" not in html and "&lt;img onerror=1&gt;" in html
