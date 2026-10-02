from __future__ import annotations

import json
from pathlib import Path

import pytest

from hornero_qa.evidence import Bundle
from hornero_qa.media import MediaError, export
from tests.conftest import SavePng, desktop

SCENARIO = "id: smoke/x\npurpose: p\ninstruction: i\nmedia: [desktop]\nproof: []\n"


def _bundle(tmp_path: Path, save_png: SavePng, run_id: str, verdict: str) -> Path:
    meta = {"scenario": "smoke/x", "product": {"shell_sha": "abc"}}
    b = Bundle.create(tmp_path / "runs", run_id, meta, SCENARIO)
    b.screenshot(save_png(desktop(), "a.png"), "desktop")
    b.screenshot(save_png(desktop(seed=3), "b.png"), "debug-only")
    b.finish({"verdict": verdict})
    return b.root


def test_exports_only_listed_media_with_provenance(tmp_path: Path, save_png: SavePng) -> None:
    root = _bundle(tmp_path, save_png, "r1", "pass")
    manifest = export([root], tmp_path / "out")
    assert [i["file"] for i in manifest["items"]] == ["smoke/x/desktop.png"]
    item = manifest["items"][0]
    assert item["product"] == {"shell_sha": "abc"} and item["run_id"] == "r1"
    side = json.loads((tmp_path / "out/smoke/x/desktop.json").read_text())
    assert side["sha256"] == item["sha256"]
    assert json.loads((tmp_path / "out/manifest.json").read_text())["schema"] == "hornero.qa.media/1"


def test_refuses_failed_runs_and_tampered_frames(tmp_path: Path, save_png: SavePng) -> None:
    with pytest.raises(MediaError, match="only passing runs"):
        export([_bundle(tmp_path, save_png, "r2", "fail")], tmp_path / "o2")
    root = _bundle(tmp_path, save_png, "r3", "pass")
    shot = next((root / "screenshots").glob("*-desktop.png"))
    shot.write_bytes(shot.read_bytes() + b"x")
    with pytest.raises(MediaError, match="sha256"):
        export([root], tmp_path / "o3")
