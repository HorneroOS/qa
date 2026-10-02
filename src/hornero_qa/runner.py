"""Deterministic scenario runner.

One attempt = boot a throwaway overlay -> wait for the desktop -> setup ->
steps (action lane, synchronised on the screen) -> proof (observation lane
only) -> classify -> evidence bundle. `--repeat N` runs N independent
attempts and reports flakiness instead of hiding it.
"""

from __future__ import annotations

import json
import platform
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hornero_qa import __version__
from hornero_qa.engines.native import NativeEngine, ProbeResult, read_image_info
from hornero_qa.evidence import Bundle
from hornero_qa.report import write_report
from hornero_qa.scenario import REPO_ROOT, Scenario
from hornero_qa.state import QAState
from hornero_qa.taxonomy import FailureClass, QAError, Verdict, is_regression
from hornero_qa.vision import (
    Anchor,
    Array,
    Rect,
    blank_frame,
    changed,
    load_frame,
    load_tokens,
    match_anchor,
    still,
)

ANCHORS_DIR = REPO_ROOT / "anchors"
COLOURS_QML = "~/.config/quickshell/services/Colours.qml"
POLL_S = 0.25
SSH_FAILED = 255


@dataclass
class RunOptions:
    image: Path
    repeat: int = 1
    boot_timeout_s: float = 240.0
    shell_timeout_s: float = 90.0
    anchors_dir: Path = ANCHORS_DIR
    mem_mb: int = 2048


@dataclass
class _Attempt:
    scenario: Scenario
    engine: NativeEngine
    bundle: Bundle
    opts: RunOptions
    deadline: float = 0.0
    actions: int = 0
    tokens: dict[str, str] = field(default_factory=dict)
    baseline: Array | None = None
    frame_path: Path = Path()
    blank_heads: list[int] = field(default_factory=list)

    # ------------------------------------------------------------ helpers --
    def grab(self, head: int = 0) -> Array:
        path = self.frame_path.with_name(f"frame-h{head}.png")
        self.engine.screenshot(path, head)
        return load_frame(path)

    def keep(self, name: str, extra: dict[str, Any] | None = None) -> list[str]:
        kept = []
        self.blank_heads = []
        for head in range(self.scenario.outputs):
            if blank_frame(self.grab(head)):
                self.blank_heads.append(head)
            suffix = f"-h{head}" if self.scenario.outputs > 1 else ""
            dst = self.bundle.screenshot(
                self.frame_path.with_name(f"frame-h{head}.png"), name + suffix, extra
            )
            kept.append(dst.name)
        return kept

    def budget(self) -> None:
        if time.monotonic() > self.deadline:
            raise QAError(FailureClass.TIMEOUT, f"wall budget {self.scenario.wall_s}s exhausted")

    def count_action(self) -> None:
        self.actions += 1
        if self.actions > self.scenario.max_actions:
            raise QAError(FailureClass.HARNESS, f"action budget {self.scenario.max_actions} exceeded")
        self.baseline = self.grab()

    def probe(self, command: str, timeout: float = 20.0) -> ProbeResult:
        r = self.engine.probe(command, timeout=timeout)
        if r.rc == SSH_FAILED and not self.engine.alive():
            raise QAError(FailureClass.BOOT, "guest died during the run")
        return r

    # ------------------------------------------------------------- phases --
    def boot(self) -> None:
        self.engine.start()
        if not self.engine.wait_ssh(self.opts.boot_timeout_s):
            cls = (
                FailureClass.BOOT if "login:" not in self.engine.serial_text() else FailureClass.PROVISIONING
            )
            raise QAError(cls, f"guest not reachable over SSH after {self.opts.boot_timeout_s:.0f}s")
        end = time.monotonic() + self.opts.shell_timeout_s
        while time.monotonic() < end:
            if self.probe("qs ipc call drawers list", timeout=10).rc == 0:
                break
            time.sleep(1.0)
        else:
            if self.probe("pgrep -x Hyprland || pgrep -x Hyprland-bin").rc != 0:
                raise QAError(FailureClass.PROVISIONING, "Hyprland session never started")
            if self.probe("pgrep -x qs || pgrep -x quickshell").rc != 0:
                raise QAError(FailureClass.PRODUCT_CRASH, "shell process not running after session start")
            raise QAError(FailureClass.PRODUCT, "shell running but its IPC never answered")
        self.bundle.action("ready", serial=_markers(self.engine.serial_text()))
        r = self.probe(f"cat {COLOURS_QML}")
        if r.rc == 0:
            qml = self.bundle.root / "logs" / "Colours.qml"
            qml.write_text(r.stdout + "\n", encoding="utf-8")
            table = "_horneroLight" if self.scenario.setup.get("theme") == "hornero-light" else "_horneroDark"
            self.tokens = load_tokens(qml, table)
        self.settle()

    def settle(self, stable_s: float = 1.0, timeout: float = 20.0) -> bool:
        end = time.monotonic() + timeout
        prev = self.grab()
        since = time.monotonic()
        while time.monotonic() < end:
            time.sleep(POLL_S)
            cur = self.grab()
            if not still(prev, cur):
                since = time.monotonic()
            elif time.monotonic() - since >= stable_s and not blank_frame(cur):
                return True
            prev = cur
        return False

    def setup(self) -> None:
        s = self.scenario.setup
        # Product setup goes through the product CLI: if horneroctl cannot
        # apply a theme or layout, that is the product failing, not QA.
        cmds: list[tuple[str, FailureClass]] = []
        if "theme" in s:
            cmds.append((f"horneroctl appearance theme set {_q(s['theme'])} --yes", FailureClass.PRODUCT))
        if "layout" in s:
            cmds.append((f"horneroctl shell preset apply {_q(s['layout'])} --yes", FailureClass.PRODUCT))
        cmds += [(c, FailureClass.HARNESS) for c in s.get("commands", [])]
        for cmd, cls in cmds:
            r = self.probe(cmd, timeout=60)
            self.bundle.action("setup", run=cmd, rc=r.rc, stdout=r.stdout[-400:], stderr=r.stderr[-400:])
            if r.rc != 0:
                out = (r.stdout + " " + r.stderr).strip()[-300:]
                raise QAError(cls, f"setup failed (rc={r.rc}): {cmd}: {out}")
        if cmds:
            # Presets/themes reload asynchronously; wait for the desktop to settle.
            time.sleep(0.5)
            self.settle(stable_s=1.5, timeout=30)

    def steps(self) -> None:
        for i, step in enumerate(self.scenario.steps):
            self.budget()
            note = step.get("note")
            kind = next((k for k in step if k != "note"), "note")
            val: Any = step.get(kind)
            self.bundle.action(kind, step=i, value=val, note=note)
            if kind == "key":
                self.count_action()
                self.engine.key(val)
            elif kind == "type":
                self.count_action()
                self.engine.type_text(val)
            elif kind == "pointer":
                self.count_action()
                self.engine.pointer(val["x"], val["y"], val.get("click"), int(val.get("glide", 1)))
            elif kind == "scroll":
                self.count_action()
                self.engine.scroll(int(val))
            elif kind == "wait":
                ok = self.wait(val)
                self.bundle.action("wait_result", step=i, ok=ok)
            elif kind == "pause":
                time.sleep(float(val))
            elif kind == "screenshot":
                self.keep(val, {"step": i})
            elif kind in ("probe", "anchor"):
                rec = self.check(kind, val, f"step {i}")
                if not rec["ok"]:
                    raise QAError(FailureClass.PRODUCT, f"step {i} {kind} failed: {rec['detail']}")

    def wait(self, spec: dict[str, Any]) -> bool:
        """Screen synchronisation. Timeouts are recorded, never asserted: proof decides."""
        ignore = [Rect(**r) for r in spec.get("ignore", [])]
        end = time.monotonic() + float(spec.get("timeout", 5.0))
        if spec.get("changed", False) and self.baseline is not None:
            while not changed(self.baseline, self.grab(), ignore):
                if time.monotonic() > end:
                    return False
                time.sleep(POLL_S / 2)
        stable = float(spec.get("stable", 0.0))
        if stable > 0:
            prev = self.grab()
            since = time.monotonic()
            while time.monotonic() - since < stable:
                if time.monotonic() > end:
                    return False
                time.sleep(POLL_S)
                cur = self.grab()
                if not still(prev, cur, ignore):
                    since = time.monotonic()
                prev = cur
        return True

    def check(self, kind: str, spec: Any, where: str) -> dict[str, Any]:
        if kind == "probe":
            rec = self.check_probe(spec)
        elif kind == "anchor":
            rec = self.check_anchor(spec)
        else:  # screenshot
            kept = self.keep(spec, {"proof": True})
            ok = not self.blank_heads
            rec = {
                "kind": "screenshot",
                "ok": ok,
                "detail": kept if ok else f"blank heads {self.blank_heads}",
            }
        rec["where"] = where
        self.bundle.assertion(rec)
        return rec

    def check_probe(self, spec: dict[str, Any]) -> dict[str, Any]:
        end = time.monotonic() + float(spec.get("retry_s", 0))
        while True:
            r = self.probe(spec["run"])
            if r.rc == SSH_FAILED:
                raise QAError(FailureClass.HARNESS, f"probe transport failed: {r.stderr[-200:]}")
            ok, why = _probe_ok(spec, r)
            if ok or time.monotonic() > end:
                return {
                    "kind": "probe",
                    "run": spec["run"],
                    "ok": ok,
                    "rc": r.rc,
                    "stdout": r.stdout[-600:],
                    "detail": why,
                }
            time.sleep(0.5)

    def check_anchor(self, spec: dict[str, Any]) -> dict[str, Any]:
        path = self.opts.anchors_dir / f"{spec['id']}.json"
        if not path.exists():
            raise QAError(FailureClass.HARNESS, f"anchor {spec['id']} not found at {path}")
        anchor = Anchor.load(path)
        expect = spec.get("expect", "present")
        end = time.monotonic() + float(spec.get("timeout", 5.0))
        while True:
            try:
                res = match_anchor(anchor, self.grab(), expect, self.tokens)
            except ValueError as exc:
                raise QAError(FailureClass.HARNESS, str(exc)) from exc
            if res.verdict or time.monotonic() > end:
                rec = {"kind": "anchor", "ok": res.verdict, "detail": res.reason} | res.as_dict()
                if not res.verdict:
                    rec["frame"] = self.keep(
                        f"anchor-miss-{spec['id'].replace('/', '-')}", {"anchor": res.as_dict()}
                    )
                return rec
            time.sleep(POLL_S)

    def proof(self) -> list[dict[str, Any]]:
        out = []
        for i, chk in enumerate(self.scenario.proof):
            kind = next(k for k in chk if k != "note")
            rec = self.check(kind, chk[kind], f"proof {i}")
            rec["note"] = chk.get("note")
            out.append(rec)
        return out

    def shell_alive(self) -> bool | None:
        """True/False from the guest; None when the probe transport failed (unknown)."""
        rc = self.engine.probe("pgrep -x qs || pgrep -x quickshell").rc
        if rc == SSH_FAILED:
            return None
        return rc == 0


def _q(s: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", s):
        raise QAError(FailureClass.HARNESS, f"unsafe setup identifier {s!r}")
    return s


def _markers(serial: str) -> list[str]:
    return [ln.strip() for ln in serial.splitlines() if ln.strip().startswith("HORNERO-")]


def _dig(data: Any, path: str) -> Any:
    for part in path.split("."):
        if isinstance(data, list):
            data = data[int(part)]
        elif isinstance(data, dict):
            data = data[part]
        else:
            raise KeyError(part)
    return data


def _probe_ok(spec: dict[str, Any], r: ProbeResult) -> tuple[bool, str]:
    out = r.stdout
    if "json" in spec:
        try:
            got = _dig(json.loads(out), spec["json"])
        except (ValueError, KeyError, IndexError) as exc:
            return False, f"json path {spec['json']!r}: {exc!r}"
        want = spec.get("equals")
        val = got if isinstance(got, str) else json.dumps(got)
        return (want is None or val == want), f"{spec['json']}={val!r} want {want!r}"
    checks = {k: spec[k] for k in ("equals", "contains", "matches", "not_contains") if k in spec}
    if not checks:
        return r.rc == 0, f"rc={r.rc}"
    for k, want in checks.items():
        if k == "equals" and out != want:
            return False, f"stdout {out[-120:]!r} != {want!r}"
        if k == "contains" and want not in out:
            return False, f"stdout lacks {want!r}"
        if k == "not_contains" and want in out:
            return False, f"stdout contains {want!r}"
        if k == "matches" and not re.search(want, out, re.M):
            return False, f"stdout does not match /{want}/"
    return True, "ok"


def _environment(scenario: Scenario, image: Path) -> dict[str, Any]:
    try:
        qemu = subprocess.run(
            ["qemu-system-x86_64", "--version"], capture_output=True, text=True, check=False, timeout=10
        )
        qemu_version = qemu.stdout.splitlines()[0] if qemu.stdout else "unknown"
    except (OSError, subprocess.TimeoutExpired):
        qemu_version = "unknown"
    return {
        "engine": "native",
        "hornero_qa": __version__,
        "host_kernel": platform.release(),
        "qemu": qemu_version,
        "image": image.resolve().name,
        "outputs": scenario.outputs,
        "resolution": "x".join(map(str, scenario.resolution)),
    }


def run_once(state: QAState, scenario: Scenario, opts: RunOptions, attempt: int = 1) -> dict[str, Any]:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    run_id = f"{stamp}-{scenario.id.replace('/', '-')}-{attempt}"
    info = read_image_info(opts.image)
    meta = {
        "scenario": scenario.id,
        "covers": scenario.covers,
        "instruction": scenario.instruction,
        "attempt": attempt,
        "product": info.get("product", {}),
        "image": info,
        "environment": _environment(scenario, opts.image),
    }
    state.ensure()
    bundle = Bundle.create(state.runs_dir, run_id, meta, scenario.text)
    engine = NativeEngine(
        state, opts.image, bundle.root, scenario.outputs, scenario.resolution, mem_mb=opts.mem_mb
    )
    att = _Attempt(scenario, engine, bundle, opts, frame_path=engine.work / "frame.png")
    verdict, cls, reason = Verdict.PASS, None, "all proof checks passed"
    try:
        att.boot()
        att.deadline = time.monotonic() + scenario.wall_s
        att.setup()
        att.steps()
        failed = [r for r in att.proof() if not r["ok"]]
        if failed:
            verdict, cls = Verdict.FAIL, FailureClass.PRODUCT
            reason = "; ".join(f"{r['where']}: {r['detail']}" for r in failed)
    except QAError as exc:
        verdict = (
            Verdict.INCONCLUSIVE
            if exc.cls not in (FailureClass.PRODUCT, FailureClass.PRODUCT_CRASH)
            else Verdict.FAIL
        )
        cls, reason = exc.cls, str(exc)
    except Exception as exc:  # the harness itself broke: never blame the product
        verdict, cls, reason = Verdict.INCONCLUSIVE, FailureClass.HARNESS, f"{type(exc).__name__}: {exc}"
    finally:
        policy = scenario.artifacts
        if engine.alive():
            try:
                # Only a definite "not running" blames the product; an SSH
                # transport failure is unknown and must not become a crash.
                if cls in (None, FailureClass.PRODUCT) and att.shell_alive() is False:
                    verdict, cls = Verdict.FAIL, FailureClass.PRODUCT_CRASH
                    reason = "shell process died during the run; " + reason
                if verdict != Verdict.PASS or policy.get("screenshots", "always") == "always":
                    att.keep("final")
                if verdict != Verdict.PASS or policy.get("logs", "always") == "always":
                    engine.collect_logs()
            except Exception as exc:  # evidence collection must not mask the verdict
                bundle.action("evidence_error", error=f"{type(exc).__name__}: {exc}")
        engine.stop()
    result = bundle.finish(
        {
            "verdict": str(verdict),
            "class": str(cls) if cls else None,
            "regression": is_regression(cls),
            "reason": reason,
            "actions": att.actions,
        }
    )
    write_report(bundle.root)
    return result | {"bundle": str(bundle.root)}


def run(state: QAState, scenario: Scenario, opts: RunOptions) -> dict[str, Any]:
    results = [run_once(state, scenario, opts, i + 1) for i in range(opts.repeat)]
    passed = sum(r["verdict"] == "pass" for r in results)
    return {
        "scenario": scenario.id,
        "attempts": len(results),
        "passed": passed,
        "flaky": 0 < passed < len(results),
        "results": results,
    }
