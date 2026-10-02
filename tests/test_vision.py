from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from hornero_qa.vision import (
    Anchor,
    Rect,
    blank_frame,
    changed,
    cut_anchor,
    delta_e_ok,
    load_frame,
    load_tokens,
    match_anchor,
    still,
)
from tests.conftest import SavePng, desktop, paint_widget


def test_blank_gate() -> None:
    assert blank_frame(np.zeros((200, 320, 3), dtype=np.float32))
    assert not blank_frame(desktop().astype(np.float32))


def test_change_and_stillness() -> None:
    a = desktop().astype(np.float32)
    b = paint_widget(desktop(), 120, 80).astype(np.float32)
    assert still(a, a.copy())
    assert changed(a, b)
    assert not changed(a, b, ignore=[Rect(0.3, 0.3, 0.4, 0.4)])


def test_oklab_distance() -> None:
    assert delta_e_ok((170, 82, 50), (170, 82, 50)) == 0.0
    assert delta_e_ok((170, 82, 50), (40, 90, 200)) > 20


def _anchor(tmp_path: Path, save_png: SavePng) -> Anchor:
    frame = save_png(paint_widget(desktop(), 120, 80), "cert.png")
    path = cut_anchor(frame, tmp_path / "anchors", "widget", (120, 80, 60, 40), ["test"], margin=24)
    return Anchor.load(path)


def test_anchor_present_absent_and_offset(tmp_path: Path, save_png: SavePng) -> None:
    anchor = _anchor(tmp_path, save_png)
    here = load_frame(save_png(paint_widget(desktop(), 120, 80), "here.png"))
    assert match_anchor(anchor, here).verdict
    gone = load_frame(save_png(desktop(), "gone.png"))
    assert match_anchor(anchor, gone, expect="absent").verdict
    assert not match_anchor(anchor, gone).verdict
    # Within the margin, the anchor is found and the offset is reported.
    shifted = load_frame(save_png(paint_widget(desktop(), 130, 84), "shifted.png"))
    res = match_anchor(anchor, shifted)
    assert res.verdict and res.offset == (10, 4)
    # Beyond the margin, a displaced widget is a failure (no full-screen search).
    far = load_frame(save_png(paint_widget(desktop(), 220, 140), "far.png"))
    assert not match_anchor(anchor, far).verdict


def test_colour_probe_catches_recolour(tmp_path: Path, save_png: SavePng) -> None:
    anchor = _anchor(tmp_path, save_png)
    anchor.color_probes = [{"token": "primary", "at": {"x": 20, "y": 10}, "size": 3, "max_delta_e": 6}]
    tokens = {"primary": "#aa5232"}
    ok = load_frame(save_png(paint_widget(desktop(), 120, 80), "ok.png"))
    assert match_anchor(anchor, ok, tokens=tokens).verdict
    blue = paint_widget(desktop(), 120, 80)
    blue[88:96, 126:174] = (50, 90, 200)
    res = match_anchor(anchor, load_frame(save_png(blue, "blue.png")), tokens=tokens)
    assert not res.verdict and res.reason == "colour_probe"


def test_cut_anchor_provenance(tmp_path: Path, save_png: SavePng) -> None:
    frame = save_png(desktop(), "d.png")
    path = cut_anchor(frame, tmp_path, "bar", (0, 0, 100, 24), ["bar"], provenance={"run_id": "r1"})
    data = json.loads(path.read_text())
    assert data["provenance"]["run_id"] == "r1" and len(data["provenance"]["capture_sha256"]) == 64


def test_load_tokens(tmp_path: Path) -> None:
    qml = tmp_path / "Colours.qml"
    body = '  "primary": "#C8643C",\n  "surface": "#1B1613"\n'
    qml.write_text("readonly property var _horneroDark: ({\n" + body + "})\n")
    assert load_tokens(qml) == {"primary": "#C8643C", "surface": "#1B1613"}


def test_cut_anchor_namespaced_id(tmp_path: Path, save_png: SavePng) -> None:
    frame = save_png(desktop(), "n.png")
    path = cut_anchor(frame, tmp_path, "launcher/search-field", (0, 0, 60, 24), ["launcher"])
    assert path == tmp_path / "launcher" / "search-field.json"
    assert Anchor.load(path).id == "launcher/search-field"
