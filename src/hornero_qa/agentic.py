"""Agentic adapters (docs/AGENTIC.md): model-agnostic driver and reviewer.

An adapter is any executable: one JSON document on stdin, one on stdout.
The launcher, not the model, enforces the driver's limits: adapters run in
a bubblewrap sandbox where the Hornero state directory (guest SSH key, QMP
sockets, other runs) does not exist; only the adapter's own work directory
is visible read-write. Network stays available for model APIs, but without
the key the guest cannot be reached.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hornero_qa.keys import KeySpecError, parse_key, text_to_chords
from hornero_qa.taxonomy import FailureClass, QAError, Verdict

DRIVER_IN = "hornero.qa.driver.in/1"
REVIEW_IN = "hornero.qa.review.in/1"
HISTORY_MAX = 20
ADAPTER_TIMEOUT_S = 120.0
ACTION_TYPES = {"key", "type", "move", "click", "scroll", "wait"}
BUTTONS = {"left", "right", "middle"}


@dataclass
class AdapterReply:
    data: dict[str, Any] | None
    error: str | None
    stderr: str = ""


def resolve_adapter_cmd(cmd: list[str], base: Path | None = None) -> list[str]:
    """Absolutize argv elements that name existing files under base (default: cwd).

    Adapters run with cwd set to their own work directory, so a repo-relative
    `--driver`/`--reviewer` command (as docs/AGENTIC.md shows) would not
    resolve there. Only elements that are existing files are rewritten;
    interpreter names, flags and opaque arguments pass through untouched.
    """
    root = base if base is not None else Path.cwd()
    out = []
    for arg in cmd:
        p = Path(arg)
        if not p.is_absolute() and (root / p).is_file():
            out.append(str(root / p))
        else:
            out.append(arg)
    return out


def _masked(key: Path | None, hidden: Path) -> list[Path]:
    """SSH key paths the sandbox must hide: an externally configured key
    (`HORNERO_QA_SSH_KEY` outside the state root) stays readable under the
    read-only `/` bind, and the sandbox shares the network namespace, so an
    adapter could otherwise SSH to the forwarded guest port. Keys already
    under the hidden root need no extra mask."""
    if key is None:
        return []
    resolved = key.expanduser()
    if resolved.is_relative_to(hidden.expanduser()):
        return []
    return [resolved] if resolved.exists() else []


def sandbox_argv(
    cmd: list[str],
    workdir: Path,
    hidden: Path,
    extra_ro: list[Path] | None = None,
    masked: list[Path] | None = None,
) -> list[str]:
    bwrap = shutil.which("bwrap")
    if bwrap is None:
        raise QAError(FailureClass.HARNESS, "agentic runs need bubblewrap (bwrap) to hide the QA state")
    argv = [
        bwrap,
        "--ro-bind",
        "/",
        "/",
        "--dev",
        "/dev",
        "--proc",
        "/proc",
        "--tmpfs",
        str(hidden),
        "--bind",
        str(workdir),
        str(workdir),
    ]
    for path in extra_ro or []:
        argv += ["--ro-bind", str(path), str(path)]
    for path in masked or []:
        argv += ["--ro-bind", "/dev/null", str(path)]
    return [
        *argv,
        "--unsetenv",
        "SSH_AUTH_SOCK",
        "--unsetenv",
        "SSH_AGENT_PID",
        "--unshare-pid",
        "--die-with-parent",
        "--chdir",
        str(workdir),
        "--",
        *cmd,
    ]


def run_adapter(
    cmd: list[str],
    payload: dict[str, Any],
    workdir: Path,
    hidden: Path,
    *,
    sandbox: bool = True,
    extra_ro: list[Path] | None = None,
    masked: list[Path] | None = None,
    timeout: float = ADAPTER_TIMEOUT_S,
) -> AdapterReply:
    workdir.mkdir(parents=True, exist_ok=True)
    argv = sandbox_argv(cmd, workdir, hidden, extra_ro, masked) if sandbox else cmd
    try:
        p = subprocess.run(
            argv, input=json.dumps(payload), capture_output=True, text=True, timeout=timeout, cwd=workdir
        )
    except subprocess.TimeoutExpired:
        return AdapterReply(None, f"adapter timed out after {timeout:.0f}s")
    except OSError as exc:
        raise QAError(FailureClass.HARNESS, f"adapter could not start: {exc}") from exc
    if p.returncode != 0:
        return AdapterReply(None, f"adapter exited {p.returncode}", p.stderr[-2000:])
    try:
        data = json.loads(p.stdout)
    except json.JSONDecodeError as exc:
        return AdapterReply(None, f"stdout is not one JSON document: {exc.msg}", p.stderr[-2000:])
    if not isinstance(data, dict):
        return AdapterReply(None, "stdout must be a JSON object", p.stderr[-2000:])
    return AdapterReply(data, None, p.stderr[-2000:])


def _num(v: Any, lo: float, hi: float) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool) and lo <= v <= hi


def validate_driver_reply(data: dict[str, Any], pointer: tuple[float, float] | None) -> str | None:
    """Return a refusal reason, or None when the reply is acceptable."""
    if "end" in data:
        if set(data) - {"end", "reason"}:
            return f"unknown fields {sorted(set(data) - {'end', 'reason'})}"
        if data["end"] not in ("done", "give_up"):
            return "end must be 'done' or 'give_up'"
        return None
    if set(data) - {"action", "reason"} or not isinstance(data.get("action"), dict):
        return "reply must be {action, reason} or {end, reason}"
    a = data["action"]
    kind = a.get("type")
    if kind not in ACTION_TYPES:
        return f"unknown action type {kind!r}"
    allowed = {
        "key": {"type", "chord"},
        "type": {"type", "text"},
        "move": {"type", "x", "y"},
        "click": {"type", "button"},
        "scroll": {"type", "ticks"},
        "wait": {"type", "ms"},
    }[kind]
    if set(a) - allowed:
        return f"unknown fields for {kind}: {sorted(set(a) - allowed)}"
    try:
        if kind == "key":
            parse_key(str(a.get("chord", "")))
        elif kind == "type":
            if not isinstance(a.get("text"), str) or not a["text"]:
                return "type needs non-empty text"
            text_to_chords(a["text"])
    except KeySpecError as exc:
        return str(exc)
    if kind == "move" and not (_num(a.get("x"), 0, 1) and _num(a.get("y"), 0, 1)):
        return "move needs x and y in [0, 1]"
    if kind == "click":
        if a.get("button", "left") not in BUTTONS:
            return f"button must be one of {sorted(BUTTONS)}"
        if pointer is None:
            return "click before any move"
    if kind == "scroll" and not (isinstance(a.get("ticks"), int) and -10 <= a["ticks"] <= 10 and a["ticks"]):
        return "scroll needs ticks in -10..10, not 0"
    if kind == "wait" and not _num(a.get("ms"), 1, 3000):
        return "wait needs ms in 1..3000"
    return None


def validate_review(data: dict[str, Any]) -> str | None:
    if data.get("verdict") not in ("PASS", "FAIL", "INCONCLUSIVE"):
        return "verdict must be PASS, FAIL or INCONCLUSIVE"
    cls = data.get("class")
    if cls is not None and cls not in {c.value for c in FailureClass}:
        return f"class {cls!r} is not in the taxonomy"
    reasons = data.get("reasons")
    if not isinstance(reasons, list) or not all(isinstance(r, dict) for r in reasons):
        return "reasons must be a list of objects"
    return None


def apply_review(
    verdict: Verdict, cls: FailureClass | None, driver_end: str | None, review: dict[str, Any]
) -> tuple[Verdict, FailureClass | None, bool, str]:
    """The harness enforces precedence; the reviewer only types and explains.

    Returns (verdict, class, needs_review, note).
    """
    rv, rcls = review["verdict"], review.get("class")
    if cls in (FailureClass.HARNESS, FailureClass.BOOT, FailureClass.PROVISIONING):
        return verdict, cls, False, "infra signal: reviewer ignored"
    if verdict == Verdict.FAIL and cls == FailureClass.DRIVER:
        if rcls == FailureClass.PRODUCT.value and rv == "FAIL" and review.get("reasons"):
            return Verdict.FAIL, FailureClass.PRODUCT, False, "reviewer found a product cause"
        return verdict, cls, False, "driver failure stands"
    if verdict == Verdict.PASS and driver_end == "done" and rv == "FAIL":
        new = FailureClass(rcls) if rcls else FailureClass.INCONCLUSIVE
        return Verdict.FAIL, new, True, "deterministic proof passed but the reviewer disagrees"
    return verdict, cls, False, "reviewer agrees or cannot change this verdict"
