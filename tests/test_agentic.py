from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest
from PIL import Image

from hornero_qa.agentic import (
    _masked,
    apply_review,
    resolve_adapter_cmd,
    run_adapter,
    sandbox_argv,
    validate_driver_reply,
    validate_review,
)
from hornero_qa.engines.native import ProbeResult
from hornero_qa.evidence import Bundle
from hornero_qa.runner import RunOptions, _Attempt
from hornero_qa.scenario import parse
from hornero_qa.taxonomy import FailureClass, QAError, Verdict
from tests.conftest import desktop

if TYPE_CHECKING:
    from hornero_qa.engines.native import NativeEngine

REPO = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("reply", "pointer", "ok"),
    [
        ({"end": "done", "reason": "x"}, None, True),
        ({"end": "maybe"}, None, False),
        ({"action": {"type": "key", "chord": "super+d"}, "reason": "r"}, None, True),
        ({"action": {"type": "key", "chord": "hyper+d"}}, None, False),
        ({"action": {"type": "move", "x": 0.5, "y": 1.2}}, None, False),
        ({"action": {"type": "click", "button": "left"}}, None, False),
        ({"action": {"type": "click", "button": "left"}}, (0.5, 0.5), True),
        ({"action": {"type": "scroll", "ticks": 0}}, None, False),
        ({"action": {"type": "wait", "ms": 5000}}, None, False),
        ({"action": {"type": "key", "chord": "a", "extra": 1}}, None, False),
        ({"action": {"type": "ssh", "cmd": "id"}}, None, False),
    ],
)
def test_driver_replies(reply: dict[str, Any], pointer: tuple[float, float] | None, ok: bool) -> None:
    assert (validate_driver_reply(reply, pointer) is None) is ok


def test_review_validation_and_precedence() -> None:
    assert validate_review({"verdict": "PASS", "class": None, "reasons": []}) is None
    assert validate_review({"verdict": "OK", "reasons": []}) is not None
    assert validate_review({"verdict": "FAIL", "class": "nope", "reasons": []}) is not None
    fail_product = {"verdict": "FAIL", "class": "product", "reasons": [{"proof": "p0", "text": "x"}]}
    # A reviewer can never rescue a deterministic product failure.
    v, c, _, _ = apply_review(Verdict.FAIL, FailureClass.PRODUCT, "done", {"verdict": "PASS", "reasons": []})
    assert (v, c) == (Verdict.FAIL, FailureClass.PRODUCT)
    # It may turn a driver give-up into a product failure, with evidence only.
    assert apply_review(Verdict.FAIL, FailureClass.DRIVER, "give_up", fail_product)[1] is FailureClass.PRODUCT
    no_evidence = fail_product | {"reasons": []}
    assert apply_review(Verdict.FAIL, FailureClass.DRIVER, "give_up", no_evidence)[1] is FailureClass.DRIVER
    # Driver done + reviewer FAIL over a deterministic pass: FAIL, flagged.
    v, c, needs, _ = apply_review(Verdict.PASS, None, "done", fail_product)
    assert (v, c, needs) == (Verdict.FAIL, FailureClass.PRODUCT, True)
    # Infra signals ignore the reviewer.
    assert apply_review(Verdict.INCONCLUSIVE, FailureClass.BOOT, None, fail_product)[1] is FailureClass.BOOT


def test_run_adapter_contract(tmp_path: Path) -> None:
    echo = [
        sys.executable,
        "-c",
        "import json,sys; d=json.load(sys.stdin); print(json.dumps({'end':'done','reason':str(d['turn'])}))",
    ]
    reply = run_adapter(echo, {"turn": 7}, tmp_path / "w", tmp_path / "hidden", sandbox=False)
    assert reply.data == {"end": "done", "reason": "7"}
    junk = [sys.executable, "-c", "print('not json')"]
    assert run_adapter(junk, {}, tmp_path / "w", tmp_path / "h", sandbox=False).error
    crash = [sys.executable, "-c", "import sys; sys.exit(3)"]
    assert "exited 3" in (run_adapter(crash, {}, tmp_path / "w", tmp_path / "h", sandbox=False).error or "")


def test_sandbox_hides_state(tmp_path: Path) -> None:
    argv = sandbox_argv(["true"], tmp_path / "work", tmp_path / "state") if _has_bwrap() else []
    if argv:
        assert ["--tmpfs", str(tmp_path / "state")] == argv[argv.index("--tmpfs") : argv.index("--tmpfs") + 2]


def test_sandbox_masks_external_ssh_key_and_agent(tmp_path: Path) -> None:
    key = tmp_path / "elsewhere" / "id_ed25519"
    key.parent.mkdir()
    key.write_text("secret")
    assert _masked(key, tmp_path / "state") == [key]
    assert _masked(tmp_path / "state" / "ssh" / "id_ed25519", tmp_path / "state") == []
    assert _masked(None, tmp_path / "state") == []
    assert _masked(tmp_path / "missing", tmp_path / "state") == []
    if not _has_bwrap():
        return
    argv = sandbox_argv(["true"], tmp_path / "work", tmp_path / "state", masked=[key])
    at = argv.index("/dev/null")
    assert ["--ro-bind", "/dev/null", str(key)] == argv[at - 1 : at + 2]
    assert "--unsetenv" in argv and "SSH_AUTH_SOCK" in argv and "SSH_AGENT_PID" in argv


def _has_bwrap() -> bool:
    import shutil

    return shutil.which("bwrap") is not None


class FakeEngine:
    def __init__(self, work: Path) -> None:
        self.work = work
        self.calls: list[tuple[Any, ...]] = []

    def screenshot(self, dest: Path, head: int = 0) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(desktop()).save(dest)
        return dest

    def key(self, spec: str) -> None:
        self.calls.append(("key", spec))

    def type_text(self, text: str) -> None:
        self.calls.append(("type", text))

    def pointer(self, x: float, y: float, click: str | None = None, glide: int = 1) -> None:
        self.calls.append(("pointer", x, y, click))

    def scroll(self, steps: int) -> None:
        self.calls.append(("scroll", steps))

    def probe(self, command: str, timeout: float = 20.0) -> ProbeResult:
        self.calls.append(("probe", command))
        return ProbeResult(1, "", "no running quickshell instance")


def _attempt(tmp_path: Path, max_malformed: int = 3) -> tuple[_Attempt, FakeEngine]:
    budget = f"budget: {{wall_s: 30, max_actions: 10, max_malformed: {max_malformed}}}\n"
    sc = parse(
        "id: smoke/x\npurpose: A scenario for agentic loop tests.\n"
        "instruction: Open and close the dashboard.\n"
        "proof:\n  - probe: {run: 'true'}\n" + budget
    )
    bundle = Bundle.create(tmp_path / "runs", "r1", {"scenario": sc.id}, sc.text)
    engine = FakeEngine(tmp_path / "work")
    opts = RunOptions(image=tmp_path / "x.qcow2", sandbox=False)
    native = cast("NativeEngine", engine)  # the loop only uses the input/capture surface
    att = _Attempt(sc, native, bundle, opts, frame_path=engine.work / "frame.png", hidden=tmp_path / "state")
    att.deadline = time.monotonic() + 30
    return att, engine


def test_replay_driver_end_to_end(tmp_path: Path) -> None:
    actions = tmp_path / "actions.json"
    actions.write_text(
        json.dumps(
            [
                {"type": "key", "chord": "super+d"},
                {"type": "move", "x": 0.5, "y": 0.5},
                {"type": "click", "button": "left"},
                {"type": "wait", "ms": 1},
                {"type": "key", "chord": "escape"},
            ]
        )
    )
    att, engine = _attempt(tmp_path)
    end = att.drive([sys.executable, str(REPO / "examples/adapters/replay_driver.py"), str(actions)])
    assert end == "done"
    assert engine.calls == [
        ("key", "super+d"),
        ("pointer", 0.5, 0.5, None),
        ("pointer", 0.5, 0.5, "left"),
        ("key", "escape"),
    ]
    assert len(list((att.bundle.root / "frames").glob("*.png"))) == 6


def test_malformed_budget_is_a_driver_failure(tmp_path: Path) -> None:
    att, _ = _attempt(tmp_path, max_malformed=2)
    bad = [sys.executable, "-c", 'print(\'{"action": {"type": "ssh"}}\')']
    with pytest.raises(QAError) as exc:
        att.drive(bad)
    assert exc.value.cls is FailureClass.DRIVER


def test_assertion_reviewer_reference(tmp_path: Path) -> None:
    final = tmp_path / "final.png"
    Image.fromarray(desktop()).save(final)
    payload = {
        "assertions": [{"where": "proof 0", "ok": False, "detail": "dashboard still open"}],
        "frames": {"final": str(final)},
        "driver": {"end": "done"},
    }
    cmd = [sys.executable, str(REPO / "examples/adapters/assertion_reviewer.py")]
    reply = run_adapter(cmd, payload, tmp_path / "w", tmp_path / "h", sandbox=False)
    assert reply.data is not None and validate_review(reply.data) is None
    assert reply.data["verdict"] == "FAIL" and reply.data["disagrees_with_driver"] is True


def test_unavailable_engine_is_refused_not_substituted(tmp_path: Path) -> None:
    att, engine = _attempt(tmp_path)
    att.scenario.requires = {"engine": "os-autoinst"}
    with pytest.raises(QAError) as exc:
        att.boot()
    assert exc.value.cls is FailureClass.HARNESS and engine.calls == []


def test_resolve_adapter_cmd(tmp_path: Path) -> None:
    script = tmp_path / "adapters" / "replay_driver.py"
    script.parent.mkdir()
    script.write_text("# adapter")
    (tmp_path / "actions.json").write_text("[]")
    out = resolve_adapter_cmd(
        ["python3", "adapters/replay_driver.py", "actions.json", "--flag", "super+d"], tmp_path
    )
    assert out[0] == "python3"
    assert out[1] == str(script)
    assert out[2] == str(tmp_path / "actions.json")
    assert out[3:] == ["--flag", "super+d"]
    assert resolve_adapter_cmd(["python3", "nope.py"], tmp_path) == ["python3", "nope.py"]


def test_probe_assertion_keeps_stderr(tmp_path: Path) -> None:
    att, _ = _attempt(tmp_path)
    rec = att.check_probe({"run": "perf.sh", "contains": "rss"})
    assert rec["ok"] is False and rec["stderr"] == "no running quickshell instance"
