from __future__ import annotations

import pytest

from hornero_qa.engines.native import ProbeResult
from hornero_qa.runner import _dig, _probe_ok, _q
from hornero_qa.taxonomy import FailureClass, QAError, is_regression


def r(out: str, rc: int = 0) -> ProbeResult:
    return ProbeResult(rc, out, "")


def test_probe_matchers() -> None:
    assert _probe_ok({"run": "x"}, r(""))[0]
    assert not _probe_ok({"run": "x"}, r("", 1))[0]
    assert _probe_ok({"run": "x", "equals": "up"}, r("up"))[0]
    assert not _probe_ok({"run": "x", "contains": "launcher"}, r("bar\nosd"))[0]
    assert _probe_ok({"run": "x", "not_contains": "dunst"}, r("quickshell"))[0]
    assert _probe_ok({"run": "x", "matches": r"^\d+$"}, r("12"))[0]


def test_probe_json_paths() -> None:
    out = '{"bars": [{"edge": "top", "visible": true}]}'
    assert _probe_ok({"run": "x", "json": "bars.0.edge", "equals": "top"}, r(out))[0]
    assert _probe_ok({"run": "x", "json": "bars.0.visible", "equals": "true"}, r(out))[0]
    ok, why = _probe_ok({"run": "x", "json": "bars.3.edge", "equals": "top"}, r(out))
    assert not ok and "bars.3.edge" in why
    assert not _probe_ok({"run": "x", "json": "a", "equals": "1"}, r("not json"))[0]
    assert _dig({"a": [{"b": 2}]}, "a.0.b") == 2


def test_setup_identifiers_are_not_shell() -> None:
    assert _q("cockpit-clear") == "cockpit-clear"
    with pytest.raises(QAError) as exc:
        _q("x; rm -rf ~")
    assert exc.value.cls is FailureClass.HARNESS


def test_only_product_classes_are_regressions() -> None:
    assert is_regression(FailureClass.PRODUCT) and is_regression(FailureClass.PRODUCT_CRASH)
    for cls in (FailureClass.HARNESS, FailureClass.BOOT, FailureClass.DRIVER, None):
        assert not is_regression(cls)
