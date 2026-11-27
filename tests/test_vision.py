from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from hornero_qa.vision import (
    Anchor,
    Rect,
    blank_frame,
    builtin_tokens,
    changed,
    check_contrast_probe,
    cut_anchor,
    delta_e_ok,
    hex_rgb,
    load_frame,
    match_anchor,
    oklab_delta_e,
    relative_luminance,
    rgb_to_oklab,
    scheme_tokens,
    still,
    wcag_contrast_ratio,
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


def test_scheme_tokens() -> None:
    scheme = {
        "schemaVersion": 2,
        "id": "hornero-signal-night",
        "mode": "dark",
        "palette": {"ground": "#0C0F13", "signal": "#F2A33A", "bogus": "amber"},
        "terminal": ["#000000"] * 16,
    }
    assert scheme_tokens(json.dumps(scheme)) == {"ground": "#0C0F13", "signal": "#F2A33A"}


def test_scheme_tokens_rejects_m3() -> None:
    with pytest.raises(ValueError):
        scheme_tokens(json.dumps({"primary": "#C8643C"}))


def test_builtin_tokens() -> None:
    qml = """
    readonly property var builtInThemes: ({
            "hornero-signal-night": {
                "id": "hornero-signal-night",
                "palette": {
                    "ground": "#0C0F13",
                    "signal": "#F2A33A"
                },
                "terminal": ["#0C0F13"]
            },
            "hornero-signal-day": {
                "palette": {
                    "ground": "#F4F1EA"
                }
            }
        })
    """
    assert builtin_tokens(qml, "hornero-signal-night") == {"ground": "#0C0F13", "signal": "#F2A33A"}
    assert builtin_tokens(qml, "hornero-signal-day") == {"ground": "#F4F1EA"}
    with pytest.raises(ValueError):
        builtin_tokens(qml, "hornero-dark")


def test_cut_anchor_namespaced_id(tmp_path: Path, save_png: SavePng) -> None:
    frame = save_png(desktop(), "n.png")
    path = cut_anchor(frame, tmp_path, "launcher/search-field", (0, 0, 60, 24), ["launcher"])
    assert path == tmp_path / "launcher" / "search-field.json"
    assert Anchor.load(path).id == "launcher/search-field"


def test_edge_anchor_and_out_of_bounds_color_probe_do_not_nan_crash(
    tmp_path: Path, save_png: SavePng
) -> None:
    img = paint_widget(desktop(), 0, 0)
    frame_path = save_png(img, "edge.png")
    path = cut_anchor(frame_path, tmp_path / "anchors", "edge", (0, 0, 40, 24), ["edge"])
    anchor = Anchor.load(path)
    anchor.color_probes = [
        {"token": "partial", "at": {"x": -1, "y": -1}, "size": 3, "fallback_hex": "#112233"},
        {"token": "oob", "at": {"x": 500, "y": 500}, "size": 3, "fallback_hex": "#112233"},
    ]
    res = match_anchor(anchor, load_frame(frame_path))
    assert not res.verdict
    assert res.reason == "colour_probe"
    assert res.probes[0]["got"].startswith("#")
    assert res.probes[1] == {"token": "oob", "error": "probe_out_of_bounds"}

    # Fully masked anchor fails cleanly with ValueError rather than NaN.
    anchor.mask = [{"x": 0, "y": 0, "w": 40, "h": 24}]
    with pytest.raises(ValueError, match="no unmasked interior pixels"):
        match_anchor(anchor, load_frame(frame_path))


def test_rgb_to_oklab_and_delta_e_properties() -> None:
    l_blk, a_blk, b_blk = rgb_to_oklab((0, 0, 0))
    assert (l_blk, a_blk, b_blk) == pytest.approx((0.0, 0.0, 0.0), abs=1e-6)
    l_wht, a_wht, b_wht = rgb_to_oklab((255, 255, 255))
    assert l_wht == pytest.approx(1.0, abs=1e-4)
    assert abs(a_wht) < 1e-4 and abs(b_wht) < 1e-4

    # Clamping out-of-range channel inputs does not produce NaN.
    l_oob, _, _ = rgb_to_oklab((-5, 300, 128))
    assert np.isfinite(l_oob)

    # Symmetry and perceptual ordering.
    amber = hex_rgb("#F2A33A")
    warm_amber = hex_rgb("#FFB650")
    blue = hex_rgb("#3A7FD9")
    assert oklab_delta_e(amber, amber) == 0.0
    assert oklab_delta_e(amber, blue) == pytest.approx(oklab_delta_e(blue, amber))
    assert oklab_delta_e(amber, warm_amber) < oklab_delta_e(amber, blue)


def test_wcag_contrast_ratio_aa_aaa_and_signal_palettes() -> None:
    assert relative_luminance((0, 0, 0)) == pytest.approx(0.0)
    assert relative_luminance((255, 255, 255)) == pytest.approx(1.0)
    assert wcag_contrast_ratio((0, 0, 0), (255, 255, 255)) == pytest.approx(21.0)
    assert wcag_contrast_ratio((255, 255, 255), (0, 0, 0)) == pytest.approx(21.0)
    assert wcag_contrast_ratio((128, 128, 128), (128, 128, 128)) == pytest.approx(1.0)

    # Hornero Signal Night palette pairs (services/Signal.qml)
    night_ground = hex_rgb("#0C0F13")
    night_base = hex_rgb("#13171D")
    night_ink = hex_rgb("#ECE6DA")
    night_signal = hex_rgb("#F2A33A")
    night_on_signal = hex_rgb("#1A1205")
    night_rule = hex_rgb("#2C333C")
    assert wcag_contrast_ratio(night_ink, night_ground) >= 7.0  # AAA normal text
    assert wcag_contrast_ratio(night_signal, night_base) >= 4.5  # AA normal text
    assert wcag_contrast_ratio(night_on_signal, night_signal) >= 4.5
    assert wcag_contrast_ratio(night_rule, night_base) < 3.0  # low-contrast subtle divider

    # Hornero Signal Day palette pairs (services/Signal.qml)
    day_ground = hex_rgb("#E6E1D5")
    day_base = hex_rgb("#F2EEE5")
    day_ink = hex_rgb("#1B1E22")
    day_signal = hex_rgb("#8F4B00")
    day_on_signal = hex_rgb("#FFFFFF")
    day_rule = hex_rgb("#D3CCBD")
    assert wcag_contrast_ratio(day_ink, day_ground) >= 7.0  # AAA normal text
    assert wcag_contrast_ratio(day_signal, day_base) >= 4.5  # AA normal text
    assert wcag_contrast_ratio(day_on_signal, day_signal) >= 4.5
    assert wcag_contrast_ratio(day_rule, day_base) < 3.0  # low-contrast subtle divider


def test_check_contrast_probe_pass_fail_and_guards() -> None:
    frame = np.zeros((100, 160, 3), dtype=np.float32)
    # Paint Signal Night base background, ink text patch, and low-contrast rule patch.
    frame[:, :] = hex_rgb("#13171D")
    frame[10:25, 20:40] = hex_rgb("#ECE6DA")  # high contrast ink
    frame[40:55, 20:40] = hex_rgb("#737980")  # inkFaint (UI/large-text range)
    frame[70:85, 20:40] = hex_rgb("#2C333C")  # low-contrast rule

    ok_aa = check_contrast_probe(
        frame,
        fg={"x": 25, "y": 15},
        bg={"x": 5, "y": 5},
        min_ratio=4.5,
        min_delta_e=20.0,
        fg_token="ink",
        bg_token="base",
        tokens={"ink": "#ECE6DA", "base": "#13171D"},
        max_delta_e=2.0,
        name="night-ink",
    )
    assert ok_aa.ok is True
    assert ok_aa.contrast_ratio is not None and ok_aa.contrast_ratio >= 7.0
    assert ok_aa.delta_e_ok is not None and ok_aa.delta_e_ok >= 20.0
    assert ok_aa.fg_delta_e == pytest.approx(0.0, abs=0.5)
    assert ok_aa.reason == "ok"

    # Large text / UI threshold (3.0) passes for inkFaint, while normal text (4.5) fails.
    ui_ok = check_contrast_probe(frame, fg=(25, 45), bg=(5, 5), min_ratio=3.0)
    assert ui_ok.ok is True
    aa_fail = check_contrast_probe(frame, fg=(25, 45), bg=(5, 5), min_ratio=4.5)
    assert aa_fail.ok is False
    assert "contrast_ratio" in aa_fail.reason

    # Low-contrast pair fails 3.0 UI gate.
    low_fail = check_contrast_probe(frame, fg=(25, 75), bg=(5, 5), min_ratio=3.0)
    assert low_fail.ok is False

    # Oklab min_delta_e failure and token max_delta_e failure.
    de_fail = check_contrast_probe(frame, fg=(25, 15), bg=(5, 5), min_ratio=4.5, min_delta_e=99.0)
    assert de_fail.ok is False
    assert "delta_e_ok" in de_fail.reason

    tok_fail = check_contrast_probe(frame, fg=(25, 15), bg=(5, 5), fg_hex="#0000FF", max_delta_e=5.0)
    assert tok_fail.ok is False
    assert "fg_delta_e" in tok_fail.reason

    unresolved = check_contrast_probe(frame, fg=(25, 15), bg=(5, 5), fg_token="missing", tokens={})
    assert unresolved.ok is False
    assert unresolved.error == "token_unresolved"

    # Normalized coordinates resolve properly.
    norm_ok = check_contrast_probe(
        frame, fg=(30 / 160, 17 / 100), bg=(5 / 160, 5 / 100), normalized=True, min_ratio=4.5
    )
    assert norm_ok.ok is True

    # Out-of-bounds guards never raise or return NaN.
    for bad_fg, bad_bg, norm in [
        ((-1, 10), (5, 5), False),
        ((500, 10), (5, 5), False),
        ((10, 10), (10, 500), False),
        ((1.2, 0.5), (0.1, 0.1), True),
    ]:
        oob = check_contrast_probe(frame, fg=bad_fg, bg=bad_bg, normalized=norm)
        assert oob.ok is False
        assert oob.error == "probe_out_of_bounds"

    bad_size = check_contrast_probe(frame, fg=(25, 15), bg=(5, 5), size=0)
    assert bad_size.ok is False and bad_size.error == "probe_out_of_bounds"

    nan_frame = frame.copy()
    nan_frame[15, 25] = np.nan
    nan_res = check_contrast_probe(nan_frame, fg=(25, 15), bg=(5, 5))
    assert nan_res.ok is False and nan_res.error == "probe_nan"
