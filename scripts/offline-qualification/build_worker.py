#!/usr/bin/env python3
"""Supervised Preview 33 candidate-build worker.

Waits until an execution-owned Muse process exits, enforces the existing
12 GiB build preflight (``preflight.py 8192`` — 8 GiB build VM + 4 GiB
host floor; never lowered), runs ``build-candidate.sh`` once under a
bounded timeout, and writes a terminal status only after the build VM is
verified gone. It never signs or publishes.

Status contract (audit defects A-B):

- ``pid`` is the long-lived worker process, captured once. Status writes
  must not record a transient writer subprocess.
- Every transition replaces the record. Stale ``reason``, ``iso`` and
  ``iso_sha256`` fields from an earlier phase cannot survive.

Arming contract (audit defect C): a missing, empty or invalid target-PID
file aborts. A live PID is not enough (``kill -0``); the executable token
in ``/proc/<pid>/cmdline`` must be Muse, and the ``starttime`` from
``/proc/<pid>/stat`` is the identity used to detect PID reuse.

Build contract (audit defects D-E): the build phase has a bounded
timeout. ``completed`` / ``failed`` are written only after the build VM
is gone. A pre-existing ISO in the candidate directory is deleted before
the build and can never be reported as the new candidate.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from worker import exclusive_lock, sha256_of

HERE = Path(__file__).resolve().parent
SCHEMA = "hornero-offline-build-worker/1"
# 8 GiB build VM. preflight.py adds the 4 GiB host floor, so this is the
# 12 GiB gate. There is intentionally no flag to lower it.
BUILD_VM_MIB = 8192
BUILD_VM_NAME = "hornero-build-vm"
DEFAULT_BUILD_TIMEOUT_SECONDS = 21600.0
DEFAULT_SHUTDOWN_WAIT_SECONDS = 120.0
DEFAULT_MAX_WAIT_SECONDS = 86400.0
ARTIFACT_GLOBS = ("*.iso", "*.iso.manifest.json", "candidate.sha256")
STOP_REQUESTED = False


class ArmingError(Exception):
    """Fail-closed arming refusal. ``reason`` is safe to persist."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class TargetIdentity:
    pid: int
    start_time: str
    cmdline_tokens: tuple[str, ...]


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def proc_start_time(stat_text: str) -> str:
    """Field 22 of ``/proc/<pid>/stat``, after a comm that may contain spaces."""
    end = stat_text.rfind(")")
    if end < 0 or end + 2 >= len(stat_text):
        raise ValueError("malformed /proc stat")
    fields = stat_text[end + 2 :].split()
    if len(fields) < 20:
        raise ValueError("malformed /proc stat")
    return fields[19]


def cmdline_tokens(cmdline: bytes) -> tuple[str, ...]:
    return tuple(part.decode("utf-8", errors="replace") for part in cmdline.split(b"\0") if part)


def is_muse_executable(tokens: tuple[str, ...] | list[str]) -> bool:
    """True only when the executable token is Muse, not an argument mentioning it."""
    if not tokens:
        return False
    name = Path(tokens[0]).name
    return name == "muse" or name == "muse-bin" or name.startswith("muse-bin-")


def parse_target_pid_text(text: str) -> int:
    token = text.strip()
    if not token:
        raise ArmingError("target PID file is empty; refusing to build unsupervised")
    if not token.isdigit():
        raise ArmingError("target PID file is invalid; refusing to build unsupervised")
    pid = int(token)
    if pid <= 0:
        raise ArmingError("target PID file is invalid; refusing to build unsupervised")
    return pid


def read_target_identity(pid: int, *, proc_root: Path = Path("/proc")) -> TargetIdentity | None:
    proc = proc_root / str(pid)
    try:
        stat_text = (proc / "stat").read_text(encoding="utf-8", errors="replace")
        cmdline = (proc / "cmdline").read_bytes()
    except OSError:
        return None
    try:
        start_time = proc_start_time(stat_text)
    except ValueError:
        return None
    return TargetIdentity(pid=pid, start_time=start_time, cmdline_tokens=cmdline_tokens(cmdline))


def arm_target(pid_file: Path, identity_reader: Callable[[int], TargetIdentity | None]) -> TargetIdentity:
    """Require a live Muse identity. Missing/empty files never mean 'already exited'."""
    try:
        text = pid_file.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ArmingError("target PID file missing; refusing to build unsupervised") from None
    except OSError as exc:
        raise ArmingError(f"target PID file unreadable; refusing to build unsupervised: {exc}") from exc
    pid = parse_target_pid_text(text)
    identity = identity_reader(pid)
    live_muse = (
        identity is not None
        and identity.pid == pid
        and bool(identity.start_time)
        and is_muse_executable(identity.cmdline_tokens)
    )
    if identity is None or not live_muse:
        raise ArmingError(f"target PID {pid} is not a live Muse process; refusing to arm")
    return identity


def target_still_running(
    expected: TargetIdentity,
    identity_reader: Callable[[int], TargetIdentity | None],
) -> bool:
    """Same start-time and Muse executable. PID reuse is target exit, not a new wait."""
    current = identity_reader(expected.pid)
    if current is None or current.start_time != expected.start_time:
        return False
    return is_muse_executable(current.cmdline_tokens)


class BuildStatus:
    """Atomic status file. Each update is a fresh record owned by ``worker_pid``."""

    def __init__(self, path: Path, *, worker_pid: int) -> None:
        if worker_pid <= 0:
            raise ValueError(f"worker PID must be positive: {worker_pid}")
        self.path = path
        self.worker_pid = worker_pid
        self.started_at = now()

    def update(self, status: str, **fields: Any) -> dict[str, Any]:
        data: dict[str, Any] = {
            "schema": SCHEMA,
            "status": status,
            "pid": self.worker_pid,
            "started_at": self.started_at,
            "updated_at": now(),
        }
        for key, value in fields.items():
            if value is not None:
                data[key] = value
        self.write(data)
        return data

    def write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)


def install_signal_handlers() -> None:
    def request_stop(signum: int, _frame: Any) -> None:
        global STOP_REQUESTED
        STOP_REQUESTED = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)


def sleep_interruptibly(seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if STOP_REQUESTED:
            return False
        time.sleep(min(1.0, deadline - time.monotonic()))
    return not STOP_REQUESTED


def build_preflight_command() -> list[str]:
    return [sys.executable, str(HERE / "preflight.py"), str(BUILD_VM_MIB)]


def run_build_preflight() -> tuple[bool, str]:
    result = subprocess.run(
        build_preflight_command(),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return result.returncode == 0, (result.stdout + result.stderr).strip()


def find_build_vm(ps_text: str) -> bool:
    for raw_line in ps_text.splitlines():
        line = raw_line.strip()
        if "grep" in line:
            continue
        if "qemu-system" in line and BUILD_VM_NAME in line:
            return True
    return False


def qemu_already_active(ps_text: str | None = None) -> bool:
    text = ps_text if ps_text is not None else _ps_args()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if "grep" in line:
            continue
        if "qemu-system" in line:
            return True
    return False


def build_vm_running(ps_text: str | None = None) -> bool:
    return find_build_vm(ps_text if ps_text is not None else _ps_args())


def _ps_args() -> str:
    result = subprocess.run(
        ["ps", "-u", str(os.getuid()), "-o", "args="],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ps exited {result.returncode}: {result.stderr.strip()}")
    return result.stdout


def snapshot_isos(out: Path) -> dict[str, tuple[int, int]]:
    """Map resolved ISO path to ``(inode, size)`` before the output dir is cleaned."""
    found: dict[str, tuple[int, int]] = {}
    if not out.is_dir():
        return found
    for path in out.glob("*.iso"):
        if not path.is_file():
            continue
        stat = path.stat()
        found[str(path.resolve())] = (stat.st_ino, stat.st_size)
    return found


def clean_candidate_outputs(out: Path) -> list[Path]:
    """Remove prior candidate artifacts so a stale ISO cannot be reported later."""
    out.mkdir(parents=True, exist_ok=True)
    removed: list[Path] = []
    for pattern in ARTIFACT_GLOBS:
        for path in list(out.glob(pattern)):
            if path.is_file():
                path.unlink()
                removed.append(path)
    return removed


def _survived_clean(path: Path, preexisting: dict[str, tuple[int, int]]) -> bool:
    previous = preexisting.get(str(path.resolve()))
    if previous is None:
        return False
    try:
        stat = path.stat()
    except OSError:
        return False
    return stat.st_ino == previous[0]


def select_fresh_iso(
    out: Path,
    preexisting: dict[str, tuple[int, int]],
    build_started_at: float,
) -> Path | None:
    """Return the single ISO created by this build, or None.

    A file is stale when it survived the pre-build clean (same path and
    inode) or its mtime is older than the build start. Deleted inodes are
    not denylisted: the filesystem may reuse them for the new artifact.
    Zero or several fresh ISOs fail closed — never ``ls | head -n 1``.
    """
    fresh: list[Path] = []
    for path in sorted(out.glob("*.iso")):
        if not path.is_file():
            continue
        if _survived_clean(path, preexisting) or path.stat().st_mtime < build_started_at:
            continue
        manifest = Path(str(path) + ".manifest.json")
        if not manifest.is_file():
            continue
        fresh.append(path)
    if len(fresh) != 1:
        return None
    return fresh[0]


def read_installer_revision(manifest_path: Path) -> str | None:
    try:
        loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(loaded, dict):
        return None
    revision = loaded.get("installerRevision")
    if not isinstance(revision, str) or not revision.strip():
        return None
    return revision


def candidate_command(
    host: str,
    port: int,
    identity: Path | None,
    candidate_out: Path,
) -> tuple[list[str], dict[str, str]]:
    env = {
        "OFFLINE_BUILD_HOST": host,
        "OFFLINE_BUILD_PORT": str(port),
        "CANDIDATE_OUT": str(candidate_out),
    }
    if identity is not None:
        env["OFFLINE_BUILD_IDENTITY"] = str(identity)
    return ["bash", str(HERE / "build-candidate.sh")], env


def poweroff_command(host: str, port: int, identity: Path | None) -> list[str]:
    command = ["ssh", "-p", str(port), "-o", "BatchMode=yes", "-o", "ConnectTimeout=5"]
    if identity is not None:
        command.extend(["-i", str(identity)])
    command.extend([host, "sudo -n poweroff"])
    return command


def _terminate_group(process: subprocess.Popen[Any], killer: Callable[[int, int], None]) -> None:
    with suppress(ProcessLookupError):
        killer(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        with suppress(ProcessLookupError):
            killer(process.pid, signal.SIGKILL)
        process.wait(timeout=10)


def run_bounded_build(
    command: list[str],
    env: dict[str, str],
    log_path: Path,
    timeout_seconds: float,
    *,
    popen: Callable[..., subprocess.Popen[Any]] = subprocess.Popen,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
    killer: Callable[[int, int], None] = os.killpg,
) -> int:
    """Run the candidate build. Return 124 on timeout, 130 if stop was requested."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = clock() + timeout_seconds
    with log_path.open("ab") as log:
        started = f"\n[{now()}] candidate build starting (timeout {timeout_seconds:.0f}s): {command}\n"
        log.write(started.encode())
        log.flush()
        process = popen(
            command,
            cwd=HERE.parents[1],
            env={**os.environ, **env},
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        while process.poll() is None:
            timed_out = clock() >= deadline
            if STOP_REQUESTED or timed_out:
                _terminate_group(process, killer)
                return 124 if timed_out and not STOP_REQUESTED else 130
            remaining = deadline - clock()
            sleeper(min(1.0, max(0.0, remaining)))
        return int(process.returncode or 0)


def request_build_vm_shutdown(command: list[str], log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as log:
        log.write(f"\n[{now()}] requesting build VM poweroff: {command}\n".encode())
        log.flush()
        with suppress(subprocess.TimeoutExpired, OSError):
            subprocess.run(
                command,
                stdout=log,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                timeout=30,
                check=False,
            )


def wait_for_target_exit(
    expected: TargetIdentity,
    identity_reader: Callable[[int], TargetIdentity | None],
    *,
    poll_seconds: float,
    max_wait_seconds: float,
    sleeper: Callable[[float], bool],
    clock: Callable[[], float],
) -> str:
    deadline = clock() + max_wait_seconds
    while target_still_running(expected, identity_reader):
        if STOP_REQUESTED:
            return "interrupted"
        if clock() >= deadline:
            return "blocked"
        remaining = deadline - clock()
        if remaining <= 0 or not sleeper(min(poll_seconds, remaining)):
            return "interrupted" if STOP_REQUESTED else "blocked"
    return "exited"


def wait_for_preflight(
    preflight_runner: Callable[[], tuple[bool, str]],
    *,
    poll_seconds: float,
    max_wait_seconds: float,
    sleeper: Callable[[float], bool],
    clock: Callable[[], float],
) -> tuple[str, str]:
    deadline = clock() + max_wait_seconds
    output = ""
    while True:
        if STOP_REQUESTED:
            return "interrupted", output
        ready, output = preflight_runner()
        if ready:
            return "ready", output
        if clock() >= deadline:
            return "blocked", output
        remaining = deadline - clock()
        if remaining <= 0 or not sleeper(min(poll_seconds, remaining)):
            return ("interrupted" if STOP_REQUESTED else "blocked"), output


def wait_until_vm_gone(
    vm_running: Callable[[], bool],
    *,
    timeout_seconds: float,
    sleeper: Callable[[float], bool],
    clock: Callable[[], float],
) -> bool:
    deadline = clock() + timeout_seconds
    while vm_running():
        if clock() >= deadline:
            return False
        remaining = deadline - clock()
        if remaining <= 0 or not sleeper(min(3.0, remaining)):
            return not vm_running()
    return True


@dataclass
class BuildHooks:
    identity_reader: Callable[[int], TargetIdentity | None] = read_target_identity
    preflight_runner: Callable[[], tuple[bool, str]] = run_build_preflight
    qemu_active: Callable[[], bool] = qemu_already_active
    build_runner: Callable[[list[str], dict[str, str], Path, float], int] = run_bounded_build
    shutdown_runner: Callable[[list[str], Path], None] = request_build_vm_shutdown
    vm_running: Callable[[], bool] = build_vm_running
    sleeper: Callable[[float], bool] = sleep_interruptibly
    clock: Callable[[], float] = time.monotonic
    wall_clock: Callable[[], float] = time.time


def _finish_after_shutdown(
    status: BuildStatus,
    *,
    rc: int,
    vm_gone: bool,
    candidate_out: Path,
    preexisting: dict[str, tuple[int, int]],
    build_started_at: float,
) -> int:
    """Write completed/failed only after shutdown is verified.

    If the build VM is still running, the only terminal status is blocked,
    and it never carries iso/sha fields.
    """
    if not vm_gone:
        reason = (
            "shutdown interrupted and build VM still running; refusing to report a build result"
            if STOP_REQUESTED
            else "build VM still running after poweroff wait; refusing to report terminal build state"
        )
        status.update("blocked", reason=reason, build_exit_code=rc)
        return 3
    if STOP_REQUESTED:
        status.update("interrupted", build_exit_code=rc)
        return 130
    if rc != 0:
        reason = "candidate build timed out" if rc == 124 else f"build-candidate.sh exited {rc}"
        status.update("failed", reason=reason, build_exit_code=rc)
        return rc
    iso = select_fresh_iso(candidate_out, preexisting, build_started_at)
    if iso is None:
        status.update(
            "failed",
            reason=f"fresh candidate ISO or sidecar manifest missing in {candidate_out}",
            build_exit_code=rc,
        )
        return 4
    revision = read_installer_revision(Path(str(iso) + ".manifest.json"))
    if revision is None:
        status.update("failed", reason="sidecar manifest missing installerRevision", build_exit_code=rc)
        return 4
    status.update(
        "completed",
        iso=str(iso),
        iso_sha256=sha256_of(iso),
        installer_revision=revision,
        build_exit_code=0,
    )
    return 0


def execute(args: argparse.Namespace, hooks: BuildHooks | None = None) -> int:
    global STOP_REQUESTED
    STOP_REQUESTED = False
    hooks = hooks or BuildHooks()
    install_signal_handlers()
    args.target_pid_file = args.target_pid_file.resolve()
    args.status_file = args.status_file.resolve()
    args.lock_file = args.lock_file.resolve()
    args.log_file = args.log_file.resolve()
    args.candidate_out = args.candidate_out.resolve()
    if args.build_identity is not None:
        args.build_identity = args.build_identity.resolve()
    with exclusive_lock(args.lock_file) as acquired:
        if not acquired:
            print("candidate-build worker already running; duplicate refused", file=sys.stderr)
            return 75
        status = BuildStatus(args.status_file, worker_pid=os.getpid())
        launched = False
        try:
            status.update("armed", target_pid_file=str(args.target_pid_file))
            try:
                identity = arm_target(args.target_pid_file, hooks.identity_reader)
            except ArmingError as exc:
                status.update("blocked", reason=exc.reason, target_pid_file=str(args.target_pid_file))
                return 3
            status.update("waiting-for-target-muse-exit", target_pid=identity.pid)
            waited = wait_for_target_exit(
                identity,
                hooks.identity_reader,
                poll_seconds=args.poll_seconds,
                max_wait_seconds=args.max_wait_seconds,
                sleeper=hooks.sleeper,
                clock=hooks.clock,
            )
            if waited == "interrupted":
                status.update("interrupted", target_pid=identity.pid)
                return 130
            if waited != "exited":
                status.update(
                    "blocked",
                    reason=f"target Muse PID {identity.pid} still running after deadline",
                    target_pid=identity.pid,
                )
                return 3
            status.update("waiting-for-preflight", target_pid=identity.pid)
            readiness, preflight_output = wait_for_preflight(
                hooks.preflight_runner,
                poll_seconds=args.poll_seconds,
                max_wait_seconds=args.max_wait_seconds,
                sleeper=hooks.sleeper,
                clock=hooks.clock,
            )
            if readiness == "interrupted":
                status.update("interrupted", target_pid=identity.pid)
                return 130
            if readiness != "ready":
                status.update(
                    "blocked",
                    reason="build preflight (12 GiB gate) never passed before deadline",
                    target_pid=identity.pid,
                    preflight=preflight_output,
                )
                return 3
            if hooks.qemu_active():
                status.update("blocked", reason="QEMU already active at build start; refusing to overlap")
                return 3
            preexisting = snapshot_isos(args.candidate_out)
            clean_candidate_outputs(args.candidate_out)
            build_started_at = hooks.wall_clock()
            command, env = candidate_command(
                args.build_host,
                args.build_port,
                args.build_identity,
                args.candidate_out,
            )
            status.update("building", candidate_out=str(args.candidate_out), target_pid=identity.pid)
            launched = True
            rc = hooks.build_runner(command, env, args.log_file, args.build_timeout_seconds)
            # Non-terminal. completed/failed are not written until shutdown is verified.
            status.update("shutting-down-build-vm", build_exit_code=rc, candidate_out=str(args.candidate_out))
            hooks.shutdown_runner(
                poweroff_command(args.build_host, args.build_port, args.build_identity),
                args.log_file,
            )
            vm_gone = wait_until_vm_gone(
                hooks.vm_running,
                timeout_seconds=args.shutdown_wait_seconds,
                sleeper=hooks.sleeper,
                clock=hooks.clock,
            )
            return _finish_after_shutdown(
                status,
                rc=rc,
                vm_gone=vm_gone,
                candidate_out=args.candidate_out,
                preexisting=preexisting,
                build_started_at=build_started_at,
            )
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            # A launched build may have left the VM up. Do not write failed
            # until shutdown is verified; otherwise report blocked with no ISO.
            if launched:
                with suppress(Exception):
                    hooks.shutdown_runner(
                        poweroff_command(args.build_host, args.build_port, args.build_identity),
                        args.log_file,
                    )
                vm_gone = False
                with suppress(Exception):
                    vm_gone = wait_until_vm_gone(
                        hooks.vm_running,
                        timeout_seconds=args.shutdown_wait_seconds,
                        sleeper=hooks.sleeper,
                        clock=hooks.clock,
                    )
                if not vm_gone:
                    status.update(
                        "blocked",
                        reason="build worker failed and build VM shutdown was not verified",
                        error=error,
                    )
                    return 3
            status.update("failed", error=error)
            raise


def validate_runtime_args(args: argparse.Namespace) -> str | None:
    if args.poll_seconds < 10:
        return "refusing poll interval below 10 seconds"
    if args.max_wait_seconds <= 0:
        return "refusing non-positive wait deadline"
    if args.build_timeout_seconds < 60:
        return "refusing build timeout below 60 seconds"
    if args.shutdown_wait_seconds <= 0:
        return "refusing non-positive build-VM shutdown wait"
    if args.build_port <= 0 or args.build_port > 65535:
        return f"build port out of range: {args.build_port}"
    if not str(args.build_host).strip():
        return "build host is empty"
    return None


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-pid-file", required=True, type=Path)
    parser.add_argument("--status-file", required=True, type=Path)
    parser.add_argument("--lock-file", required=True, type=Path)
    parser.add_argument("--log-file", required=True, type=Path)
    parser.add_argument("--candidate-out", required=True, type=Path)
    parser.add_argument("--build-host", required=True)
    parser.add_argument("--build-port", type=int, default=2224)
    parser.add_argument("--build-identity", type=Path, default=None)
    parser.add_argument("--poll-seconds", type=float, default=30.0)
    parser.add_argument("--max-wait-seconds", type=float, default=DEFAULT_MAX_WAIT_SECONDS)
    parser.add_argument("--build-timeout-seconds", type=float, default=DEFAULT_BUILD_TIMEOUT_SECONDS)
    parser.add_argument("--shutdown-wait-seconds", type=float, default=DEFAULT_SHUTDOWN_WAIT_SECONDS)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    refusal = validate_runtime_args(args)
    if refusal is not None:
        print(refusal, file=sys.stderr)
        return 2
    if BUILD_VM_MIB != 8192:
        print("refusing to run: build preflight gate is not 8192 MiB", file=sys.stderr)
        return 2
    return execute(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
