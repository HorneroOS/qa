from __future__ import annotations

from pathlib import Path

import pytest

from hornero_qa.engines.native import ProbeResult, qmp_socket_path
from hornero_qa.runner import SSH_FAILED, _decide, _dig, _probe_ok, _q
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


def test_decide_failed_proof_outranks_driver_give_up() -> None:
    from hornero_qa.taxonomy import Verdict

    bad = [{"where": "proof 0", "detail": "dashboard still open"}]
    v, c, why = _decide("give_up", bad)
    assert (v, c) == (Verdict.FAIL, FailureClass.PRODUCT) and "proof 0" in why
    v, c, _ = _decide("give_up", [])
    assert (v, c) == (Verdict.FAIL, FailureClass.DRIVER)
    v, c, _ = _decide("done", bad)
    assert (v, c) == (Verdict.FAIL, FailureClass.PRODUCT)
    v, c, _ = _decide(None, [])
    assert (v, c) == (Verdict.PASS, None)


def test_probe_json_paths() -> None:
    out = '{"bars": [{"edge": "top", "visible": true}]}'
    assert _probe_ok({"run": "x", "json": "bars.0.edge", "equals": "top"}, r(out))[0]
    assert _probe_ok({"run": "x", "json": "bars.0.visible", "equals": "true"}, r(out))[0]
    ok, why = _probe_ok({"run": "x", "json": "bars.3.edge", "equals": "top"}, r(out))
    assert not ok and "bars.3.edge" in why
    assert not _probe_ok({"run": "x", "json": "a", "equals": "1"}, r("not json"))[0]
    rss = '{"samples": [{"rss_kb": 51234}]}'
    assert _probe_ok({"run": "x", "json": "samples.0.rss_kb", "matches": "^[0-9]+$"}, r(rss))[0]
    assert not _probe_ok({"run": "x", "json": "samples.0.rss_kb", "equals": "1"}, r(rss))[0]
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


class _Engine:
    def __init__(self, rc: int) -> None:
        self.rc = rc

    def probe(self, command: str, timeout: float = 20.0) -> ProbeResult:
        return ProbeResult(self.rc, "", "")


@pytest.mark.parametrize(("rc", "alive"), [(0, True), (1, False), (255, None)])
def test_shell_liveness_distinguishes_transport_failure(rc: int, alive: bool | None) -> None:
    from typing import Any, cast

    from hornero_qa.runner import _Attempt

    att = cast(Any, _Attempt.__new__(_Attempt))
    att.engine = _Engine(rc)
    assert _Attempt.shell_alive(att) is alive


def test_qmp_socket_path_stays_short(tmp_path: Path) -> None:
    long_name = "20261002T032315Z-regressions-shell-24-lock-after-hyprlock-1"
    sock = qmp_socket_path(tmp_path, long_name)
    assert len(str(sock)) < 100  # AF_UNIX sun_path limit is ~107
    assert sock.parent == tmp_path
    assert qmp_socket_path(tmp_path, long_name) == sock
    assert qmp_socket_path(tmp_path, long_name + "-2") != sock


class _FlakyTransport:
    """First probe drops the connection (255), then behaves."""

    def __init__(self, rc: int = 0) -> None:
        self.calls = 0
        self.rc = rc

    def probe(self, command: str, timeout: float = 20.0) -> ProbeResult:
        self.calls += 1
        if self.calls == 1:
            return ProbeResult(SSH_FAILED, "", "")
        return ProbeResult(self.rc, "ok", "")

    def alive(self) -> bool:
        return True


def test_probe_retries_once_on_ssh_255() -> None:
    from typing import Any, cast

    from hornero_qa.runner import _Attempt

    att = cast(Any, _Attempt.__new__(_Attempt))
    att.engine = _FlakyTransport()
    r = _Attempt.probe(att, "true")
    assert (r.rc, r.stdout) == (0, "ok") and att.engine.calls == 2


def test_probe_retry_confirms_a_dead_transport() -> None:
    from typing import Any, cast

    from hornero_qa.runner import _Attempt

    att = cast(Any, _Attempt.__new__(_Attempt))
    att.engine = _FlakyTransport(rc=SSH_FAILED)
    r = _Attempt.probe(att, "true")
    assert r.rc == SSH_FAILED and att.engine.calls == 2


class _KillerCommand:
    """A guest command that breaks its own connection while the product dies
    underneath: the command always 255s, but pgrep works (shell gone)."""

    def probe(self, command: str, timeout: float = 20.0) -> ProbeResult:
        if "pgrep" in command:
            return ProbeResult(1, "", "")
        return ProbeResult(SSH_FAILED, "", "")

    def alive(self) -> bool:
        return True


class _LiveShell(_KillerCommand):
    def probe(self, command: str, timeout: float = 20.0) -> ProbeResult:
        if "pgrep" in command:
            return ProbeResult(0, "422", "")
        return ProbeResult(SSH_FAILED, "", "")


def _check_attempt(engine: object, tmp_path: Path) -> object:
    from typing import Any, cast

    from hornero_qa.evidence import Bundle
    from hornero_qa.runner import _Attempt

    att = cast(Any, _Attempt.__new__(_Attempt))
    att.engine = engine
    att.bundle = Bundle.create(tmp_path / "runs", "r1", {"scenario": "s/x"}, "text")
    return att


def test_broken_connection_with_dead_shell_is_product_crash(tmp_path: Path) -> None:
    from typing import cast

    from hornero_qa.runner import _Attempt

    att = cast(_Attempt, _check_attempt(_KillerCommand(), tmp_path))
    with pytest.raises(QAError) as exc:
        att.check_probe({"run": "qs ipc call lock lock"})
    assert exc.value.cls is FailureClass.PRODUCT_CRASH


def test_broken_connection_with_live_shell_is_harness(tmp_path: Path) -> None:
    from typing import cast

    from hornero_qa.runner import _Attempt

    att = cast(_Attempt, _check_attempt(_LiveShell(), tmp_path))
    with pytest.raises(QAError) as exc:
        att.check_probe({"run": "qs ipc call lock lock"})
    assert exc.value.cls is FailureClass.HARNESS
