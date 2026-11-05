#!/usr/bin/env python3
"""Post-execution coordinator for offline Preview 33 qualification.

This is not a replacement for the current Muse session: Muse
`resume` is interactive and cannot safely be driven unattended. Instead,
after the supervised worker reaches a terminal state, this coordinator
starts one new headless `muse exec` review with a persisted prompt. It
runs at most once, under its own lock and systemd control group, and it
never starts while a qualification VM is active.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from worker import exclusive_lock

TERMINAL_WORKER_STATUSES = {"completed", "failed", "blocked", "interrupted"}
STOP_REQUESTED = False


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_status(path: Path, **fields: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data.update(loaded)
        except (OSError, json.JSONDecodeError):
            pass
    data.update(fields, updated_at=now(), pid=os.getpid())
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def read_worker_status(path: Path) -> str:
    try:
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "missing"
    status = data.get("status")
    return status if isinstance(status, str) else "missing"


def install_signal_handlers() -> None:
    def request_stop(signum: int, _frame: Any) -> None:
        global STOP_REQUESTED
        STOP_REQUESTED = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)


def wait_for_terminal(
    worker_status_file: Path,
    coordinator_status_file: Path,
    *,
    poll_seconds: float,
    max_wait_seconds: float,
    status_reader: Callable[[Path], str] = read_worker_status,
    sleeper: Callable[[float], bool] | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> str:
    deadline = clock() + max_wait_seconds
    observed = ""

    def sleep(seconds: float) -> bool:
        if sleeper is not None:
            return sleeper(seconds)
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if STOP_REQUESTED:
                return False
            time.sleep(min(1.0, end - time.monotonic()))
        return not STOP_REQUESTED

    while clock() < deadline:
        if STOP_REQUESTED:
            return "interrupted"
        current = status_reader(worker_status_file)
        if current in TERMINAL_WORKER_STATUSES:
            return current
        if current != observed:
            observed = current
            write_status(
                coordinator_status_file,
                status="waiting-for-worker",
                worker_status=current,
                worker_status_file=str(worker_status_file),
            )
        remaining = deadline - clock()
        if remaining <= 0:
            return "blocked"
        if not sleep(min(poll_seconds, remaining)):
            return "interrupted"
    return "blocked"


def build_review_command(args: argparse.Namespace) -> list[str]:
    return [
        args.muse_bin,
        "exec",
        "--yolo",
        "--workspace",
        str(args.workspace),
        "--prompt-file",
        str(args.prompt_file),
    ]


def run_review(command: list[str], log_file: Path, *, timeout_seconds: float) -> int:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout_seconds
    with log_file.open("ab") as log:
        log.write(f"\n[{now()}] coordinator starting headless review: {command}\n".encode())
        log.flush()
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        while process.poll() is None:
            if STOP_REQUESTED:
                process.terminate()
                try:
                    return process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    process.kill()
                    return process.wait(timeout=10)
            if time.monotonic() >= deadline:
                process.kill()
                process.wait(timeout=10)
                return 124
            time.sleep(1)
        return int(process.returncode or 0)


def execute(args: argparse.Namespace) -> int:
    install_signal_handlers()
    args.worker_status_file = args.worker_status_file.resolve()
    args.status_file = args.status_file.resolve()
    args.lock_file = args.lock_file.resolve()
    args.log_file = args.log_file.resolve()
    args.prompt_file = args.prompt_file.resolve()
    args.workspace = args.workspace.resolve()
    if not args.prompt_file.is_file():
        print(f"prompt file not found: {args.prompt_file}", file=sys.stderr)
        return 2
    if not args.workspace.is_dir():
        print(f"workspace not found: {args.workspace}", file=sys.stderr)
        return 2
    if shutil.which(args.muse_bin) is None and not Path(args.muse_bin).is_file():
        print(f"Muse executable not found: {args.muse_bin}", file=sys.stderr)
        return 2
    with exclusive_lock(args.lock_file) as acquired:
        if not acquired:
            print("post-execution coordinator already running; duplicate refused", file=sys.stderr)
            return 75
        write_status(
            args.status_file,
            schema="hornero-offline-coordinator/1",
            status="armed",
            worker_status_file=str(args.worker_status_file),
            prompt_file=str(args.prompt_file),
        )
        terminal = wait_for_terminal(
            args.worker_status_file,
            args.status_file,
            poll_seconds=args.poll_seconds,
            max_wait_seconds=args.max_wait_seconds,
        )
        if terminal == "interrupted":
            write_status(args.status_file, status="interrupted")
            return 130
        if terminal == "blocked":
            write_status(args.status_file, status="blocked", reason="worker wait deadline expired")
            return 3
        write_status(args.status_file, status="review-ready", worker_status=terminal)
        command = build_review_command(args)
        write_status(args.status_file, status="reviewing", review_command=command)
        code = run_review(command, args.log_file, timeout_seconds=args.review_timeout_seconds)
        if STOP_REQUESTED:
            write_status(args.status_file, status="interrupted", review_exit_code=code)
            return 130
        status = "review-completed" if code == 0 else "review-failed"
        write_status(args.status_file, status=status, review_exit_code=code)
        return code


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker-status-file", required=True, type=Path)
    parser.add_argument("--status-file", required=True, type=Path)
    parser.add_argument("--lock-file", required=True, type=Path)
    parser.add_argument("--log-file", required=True, type=Path)
    parser.add_argument("--prompt-file", required=True, type=Path)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--muse-bin", default="muse")
    parser.add_argument("--poll-seconds", type=float, default=60.0)
    parser.add_argument("--max-wait-seconds", type=float, default=172800.0)
    parser.add_argument("--review-timeout-seconds", type=float, default=21600.0)
    args = parser.parse_args(argv)
    if args.poll_seconds < 10:
        parser.error("--poll-seconds must be at least 10")
    return args


def main(argv: list[str]) -> int:
    return execute(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
