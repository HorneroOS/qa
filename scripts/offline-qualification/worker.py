#!/usr/bin/env python3
"""Supervised offline worker for Preview 33 qualification.

The worker is intended to run as a systemd user service. It waits until
Muse is no longer holding RAM and the existing resource preflight
passes, then invokes run.py exactly once. It does not implement a second
QA runner: run.py remains responsible for VM serialization, checkpoints,
evidence and per-cell state.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from contextlib import contextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
RUNNER_VM_MIB = 4096  # Must match run.py's fixed guest RAM.
STOP_REQUESTED = False


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_muse_processes(ps_text: str, *, own_pid: int | None = None) -> list[dict[str, Any]]:
    """Find Muse executables in `ps -o pid=,args=` output.

    Only the executable token is considered, so arguments or paths merely
    containing "muse" cannot keep the worker waiting forever.
    """
    found: list[dict[str, Any]] = []
    for raw_line in ps_text.splitlines():
        line = raw_line.strip()
        if not line or not line.split(maxsplit=1)[0].isdigit():
            continue
        pid_text, _, args = line.partition(" ")
        pid = int(pid_text)
        if pid == own_pid:
            continue
        tokens = args.strip().split()
        if not tokens:
            continue
        executable = Path(tokens[0]).name
        if executable == "muse" or executable == "muse-bin" or executable.startswith("muse-bin-"):
            found.append({"pid": pid, "executable": executable})
    return found


def ps_output() -> str:
    result = subprocess.run(
        ["ps", "-u", str(os.getuid()), "-o", "pid=,args="],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ps exited {result.returncode}: {result.stderr.strip()}")
    return result.stdout


def list_muse_processes(
    target_pids: set[int] | None = None,
) -> list[dict[str, Any]]:
    processes = find_muse_processes(ps_output(), own_pid=os.getpid())
    if target_pids is None:
        return processes
    return [item for item in processes if int(item["pid"]) in target_pids]


def read_pid_file(path: Path) -> set[int]:
    pids: set[int] = set()
    for token in path.read_text(encoding="utf-8").replace(",", " ").split():
        pid = int(token)
        if pid <= 0:
            raise ValueError(f"PID must be positive: {pid}")
        pids.add(pid)
    if not pids:
        raise ValueError(f"PID file is empty: {path}")
    return pids


def resolve_wait_pids(args: argparse.Namespace) -> set[int] | None:
    if not args.wait_for_pid and args.wait_for_pid_file is None:
        return None
    pids = set(args.wait_for_pid)
    if args.wait_for_pid_file is not None:
        pids.update(read_pid_file(args.wait_for_pid_file.resolve()))
    return pids


def _option_value(tokens: list[str], option: str) -> str | None:
    try:
        index = tokens.index(option)
    except ValueError:
        return None
    return tokens[index + 1] if index + 1 < len(tokens) else None


def find_runner_qemu_processes(ps_text: str) -> list[dict[str, Any]]:
    """Find QEMU processes launched by run.py using stable CLI markers."""
    found: list[dict[str, Any]] = []
    for raw_line in ps_text.splitlines():
        line = raw_line.strip()
        if not line or not line.split(maxsplit=1)[0].isdigit():
            continue
        pid_text, _, args = line.partition(" ")
        tokens = args.strip().split()
        if not tokens or Path(tokens[0]).name != "qemu-system-x86_64":
            continue
        name = _option_value(tokens, "-name")
        pidfile = _option_value(tokens, "-pidfile")
        if name and pidfile and name.startswith("hornero-install-p33off-"):
            found.append({"pid": int(pid_text), "name": name, "pidfile": pidfile})
    return found


def list_runner_qemu_processes() -> list[dict[str, Any]]:
    return find_runner_qemu_processes(ps_output())


def stop_new_runner_qemu_processes(
    preexisting_pids: set[int],
    *,
    process_provider: Callable[[], list[dict[str, Any]]] = list_runner_qemu_processes,
    signaler: Callable[[int, int], None] = os.kill,
    sleeper: Callable[[float], Any] = time.sleep,
) -> list[int]:
    """Terminate only runner QEMU processes created after the snapshot."""
    targets = [item for item in process_provider() if int(item["pid"]) not in preexisting_pids]
    stopped: list[int] = []
    for item in targets:
        pid = int(item["pid"])
        try:
            signaler(pid, signal.SIGTERM)
            stopped.append(pid)
        except ProcessLookupError:
            continue
    for _ in range(10):
        remaining = [item for item in process_provider() if int(item["pid"]) in stopped]
        if not remaining:
            return stopped
        sleeper(1.0)
    for item in process_provider():
        pid = int(item["pid"])
        if pid in stopped:
            try:
                signaler(pid, signal.SIGKILL)
            except ProcessLookupError:
                continue
    return stopped


class StatusWriter:
    def __init__(self, path: Path, *, state_dir: Path, iso_path: Path, cells: str) -> None:
        self.path = path
        self.data: dict[str, Any] = {
            "schema": "hornero-offline-worker/1",
            "status": "armed",
            "pid": os.getpid(),
            "started_at": now(),
            "updated_at": now(),
            "state_dir": str(state_dir),
            "iso": str(iso_path),
            "cells": cells,
        }
        self.write()

    def update(self, status: str, **fields: Any) -> None:
        self.data.update(status=status, updated_at=now(), **fields)
        self.write()

    def write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(self.data, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)


@contextmanager
def exclusive_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+", encoding="utf-8")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        handle.seek(0)
        handle.truncate()
        handle.write(f"{os.getpid()}\n")
        handle.flush()
        yield True
    finally:
        handle.close()


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


def run_preflight(vm_mib: int, state_dir: Path) -> tuple[bool, str]:
    env = {**os.environ, "OFFLINE_STATE_DIR": str(state_dir.parent)}
    result = subprocess.run(
        [sys.executable, str(HERE / "preflight.py"), str(vm_mib)],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
        check=False,
    )
    return result.returncode == 0, (result.stdout + result.stderr).strip()


def wait_until_ready(
    status: StatusWriter,
    *,
    wait_for_muse: bool,
    vm_mib: int,
    state_dir: Path,
    poll_seconds: float,
    max_wait_seconds: float,
    target_pids: set[int] | None = None,
    process_provider: Callable[[], list[dict[str, Any]]] = list_muse_processes,
    preflight_runner: Callable[[int, Path], tuple[bool, str]] = run_preflight,
    sleeper: Callable[[float], bool] = sleep_interruptibly,
    clock: Callable[[], float] = time.monotonic,
) -> str:
    """Return ready, blocked, or interrupted without busy-looping."""
    deadline = clock() + max_wait_seconds
    last_phase = ""
    while clock() < deadline:
        if STOP_REQUESTED:
            return "interrupted"
        if wait_for_muse:
            processes = process_provider()
            if processes:
                phase = "waiting-for-target-muse-exit" if target_pids is not None else "waiting-for-muse-exit"
                if phase != last_phase:
                    status.update(phase, muse_processes=processes)
                    last_phase = phase
                remaining = deadline - clock()
                if remaining <= 0:
                    return "blocked"
                if not sleeper(min(poll_seconds, remaining)):
                    return "interrupted"
                continue
        ready, output = preflight_runner(vm_mib, state_dir)
        if clock() >= deadline:
            return "blocked"
        if ready:
            status.update("resources-ready", preflight=output)
            return "ready"
        phase = "waiting-for-resources"
        if phase != last_phase:
            status.update(phase, preflight=output)
            last_phase = phase
        remaining = deadline - clock()
        if remaining <= 0:
            return "blocked"
        if not sleeper(min(poll_seconds, remaining)):
            return "interrupted"
    return "blocked"


def build_runner_command(args: argparse.Namespace) -> list[str]:
    command = [
        sys.executable,
        str(HERE / "run.py"),
        "--iso",
        str(args.iso),
        "--cells",
        args.cells,
        "--state-dir",
        str(args.state_dir),
    ]
    if (args.state_dir / "manifest.json").exists():
        command.append("--resume")
    if args.installer_repo is not None:
        command.extend(["--installer-repo", str(args.installer_repo)])
    if args.expected_sha256:
        command.extend(["--expected-sha256", args.expected_sha256])
    return command


def run_runner(command: list[str], log_path: Path) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    preexisting_qemu = {int(item["pid"]) for item in list_runner_qemu_processes()}
    with log_path.open("ab") as log:
        process = subprocess.Popen(
            command,
            cwd=HERE.parents[1],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        while process.poll() is None:
            if STOP_REQUESTED:
                with suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGTERM)
                try:
                    code = process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    with suppress(ProcessLookupError):
                        os.killpg(process.pid, signal.SIGKILL)
                    code = process.wait(timeout=10)
                # run.py launches QEMU in a separate session; stop only the
                # PID-verified QEMU processes created by this runner.
                stop_new_runner_qemu_processes(preexisting_qemu)
                return int(code or 0)
            time.sleep(1)
        return int(process.returncode or 0)


def verify_expected_iso(status: StatusWriter, iso_path: Path, expected: str | None) -> bool:
    if not expected:
        return True
    status.update("verifying-iso")
    actual = sha256_of(iso_path)
    if actual.lower() != expected.lower():
        status.update("blocked", reason="ISO SHA-256 mismatch", actual_sha256=actual)
        return False
    status.update("iso-verified", actual_sha256=actual)
    return True


def execute(args: argparse.Namespace) -> int:
    install_signal_handlers()
    args.iso = args.iso.resolve()
    args.state_dir = args.state_dir.resolve()
    args.status_file = args.status_file.resolve()
    args.lock_file = args.lock_file.resolve()
    args.log_file = args.log_file.resolve()
    if args.installer_repo is not None:
        args.installer_repo = args.installer_repo.resolve()
    if not args.iso.is_file():
        print(f"ISO not found: {args.iso}", file=sys.stderr)
        return 2
    try:
        target_pids = resolve_wait_pids(args)
    except (OSError, ValueError) as exc:
        print(f"invalid Muse wait target: {exc}", file=sys.stderr)
        return 2
    with exclusive_lock(args.lock_file) as acquired:
        if not acquired:
            print("offline worker already running for this state; duplicate refused", file=sys.stderr)
            return 75
        status = StatusWriter(
            args.status_file,
            state_dir=args.state_dir,
            iso_path=args.iso,
            cells=args.cells,
        )
        try:
            status.update(
                "armed",
                target_pids=sorted(target_pids) if target_pids is not None else "all-muse",
            )
            if not verify_expected_iso(status, args.iso, args.expected_sha256):
                return 3
            readiness = wait_until_ready(
                status,
                wait_for_muse=not args.no_wait_for_muse,
                vm_mib=RUNNER_VM_MIB,
                state_dir=args.state_dir,
                poll_seconds=args.poll_seconds,
                max_wait_seconds=args.max_wait_seconds,
                target_pids=target_pids,
                process_provider=lambda: list_muse_processes(target_pids),
            )
            if readiness == "interrupted":
                status.update("interrupted")
                return 130
            if readiness != "ready":
                status.update("blocked", reason="resource wait deadline expired")
                return 3
            # The ISO could have been replaced during a long wait; verify it
            # again immediately before run.py pins its own computed digest.
            if not verify_expected_iso(status, args.iso, args.expected_sha256):
                return 3
            command = build_runner_command(args)
            status.update("running", runner_command=command, runner_log=str(args.log_file))
            args.log_file.parent.mkdir(parents=True, exist_ok=True)
            with args.log_file.open("a", encoding="utf-8") as log:
                log.write(f"\n[{now()}] worker starting runner: {command}\n")
            code = run_runner(command, args.log_file)
            if STOP_REQUESTED:
                status.update("interrupted", runner_exit_code=code)
                return 130
            if code == 0:
                status.update("completed", runner_exit_code=code)
            elif code == 3:
                status.update("blocked", runner_exit_code=code)
            else:
                status.update("failed", runner_exit_code=code)
            return code
        except Exception as exc:
            status.update("failed", error=f"{type(exc).__name__}: {exc}")
            raise


def show_status(path: Path) -> int:
    if not path.is_file():
        print(f"no worker status file: {path}")
        return 1
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    print(f"status: {data.get('status')}")
    print(f"updated: {data.get('updated_at')}")
    print(f"state: {data.get('state_dir')}")
    print(f"runner exit: {data.get('runner_exit_code', '-')}")
    if data.get("reason"):
        print(f"reason: {data['reason']}")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="action")
    subcommands.add_parser("run", help="wait for resources and execute run.py once")
    status_parser = subcommands.add_parser("status", help="show persisted worker status")
    status_parser.add_argument("--status-file", required=True, type=Path)

    # `run` is the default for systemd ExecStart compatibility.
    if argv and argv[0] not in {"run", "status", "-h", "--help"}:
        argv = ["run", *argv]
    if argv and argv[0] == "run":
        run_parser = subcommands.choices["run"]  # type: ignore[attr-defined]
        run_parser.add_argument("--iso", required=True, type=Path)
        run_parser.add_argument("--cells", required=True)
        run_parser.add_argument("--state-dir", required=True, type=Path)
        run_parser.add_argument("--status-file", required=True, type=Path)
        run_parser.add_argument("--lock-file", required=True, type=Path)
        run_parser.add_argument("--log-file", required=True, type=Path)
        run_parser.add_argument("--installer-repo", type=Path, default=None)
        run_parser.add_argument("--expected-sha256", default=None)
        run_parser.add_argument("--wait-for-pid", action="append", type=int, default=[])
        run_parser.add_argument("--wait-for-pid-file", type=Path, default=None)
        run_parser.add_argument("--poll-seconds", type=float, default=60.0)
        run_parser.add_argument("--max-wait-seconds", type=float, default=86400.0)
        run_parser.add_argument("--no-wait-for-muse", action="store_true")
    args = parser.parse_args(argv)
    if args.action is None:
        parser.print_help()
        raise SystemExit(2)
    return args


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if args.action == "status":
        return show_status(args.status_file)
    if args.poll_seconds < 10:
        print("refusing poll interval below 10 seconds", file=sys.stderr)
        return 2
    return execute(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
