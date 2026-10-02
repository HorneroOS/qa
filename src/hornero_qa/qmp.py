"""Minimal QMP client (stdlib only): HID input and framebuffer capture.

The action lane of a scenario is driven exclusively through this module:
`input-send-event` key and absolute-pointer events reach the guest through
the emulated keyboard and USB tablet, exactly like a user's hardware.
"""

from __future__ import annotations

import json
import socket
import time
from pathlib import Path
from typing import Any

# QEMU absolute pointer range for `input-send-event` abs axes.
ABS_MAX = 32767


class QMPError(RuntimeError):
    """A QMP command failed or the connection broke."""


class QMP:
    def __init__(self, path: str | Path, timeout: float = 30.0) -> None:
        self.path = str(path)
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(timeout)
        self.sock.connect(self.path)
        self._buf = b""
        greeting = self._read()
        if "QMP" not in greeting:
            raise QMPError(f"unexpected QMP greeting: {greeting}")
        self.cmd("qmp_capabilities")

    @classmethod
    def wait(cls, path: str | Path, deadline_s: float = 30.0) -> QMP:
        """Connect once QEMU has created the socket."""
        end = time.monotonic() + deadline_s
        last: Exception | None = None
        while time.monotonic() < end:
            try:
                return cls(path)
            except OSError as exc:  # not created yet / refused
                last = exc
                time.sleep(0.1)
        raise QMPError(f"QMP socket {path} not ready: {last}")

    def _read(self) -> dict[str, Any]:
        while b"\n" not in self._buf:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise QMPError("QMP connection closed")
            self._buf += chunk
        line, self._buf = self._buf.split(b"\n", 1)
        data: dict[str, Any] = json.loads(line)
        return data

    def cmd(self, execute: str, **arguments: Any) -> Any:
        msg: dict[str, Any] = {"execute": execute}
        if arguments:
            msg["arguments"] = arguments
        self.sock.sendall(json.dumps(msg).encode() + b"\n")
        while True:
            resp = self._read()
            if "event" in resp:
                continue
            if "error" in resp:
                raise QMPError(f"{execute}: {resp['error']}")
            return resp.get("return")

    # ---------------------------------------------------------- observation --
    def screendump(self, png_path: str | Path) -> None:
        self.cmd("screendump", filename=str(png_path), format="png")

    # ---------------------------------------------------------------- input --
    @staticmethod
    def _key_event(qcode: str, down: bool) -> dict[str, Any]:
        return {"type": "key", "data": {"down": down, "key": {"type": "qcode", "data": qcode}}}

    def chord(self, qcodes: list[str], hold_s: float = 0.06) -> None:
        """Press qcodes in order, hold, release in reverse order."""
        self.cmd("input-send-event", events=[self._key_event(q, True) for q in qcodes])
        time.sleep(hold_s)
        self.cmd("input-send-event", events=[self._key_event(q, False) for q in reversed(qcodes)])

    def pointer_abs(self, x: float, y: float) -> None:
        """Move the tablet pointer to normalized coordinates (0..1) of the output."""
        ax = round(min(max(x, 0.0), 1.0) * ABS_MAX)
        ay = round(min(max(y, 0.0), 1.0) * ABS_MAX)
        self.cmd(
            "input-send-event",
            events=[
                {"type": "abs", "data": {"axis": "x", "value": ax}},
                {"type": "abs", "data": {"axis": "y", "value": ay}},
            ],
        )

    def button(self, button: str, down: bool) -> None:
        self.cmd("input-send-event", events=[{"type": "btn", "data": {"down": down, "button": button}}])

    def click(self, button: str = "left", hold_s: float = 0.05) -> None:
        self.button(button, True)
        time.sleep(hold_s)
        self.button(button, False)

    def scroll(self, steps: int) -> None:
        """Positive steps scroll down, negative up (wheel buttons)."""
        button = "wheel-down" if steps > 0 else "wheel-up"
        for _ in range(abs(steps)):
            self.click(button, hold_s=0.01)

    def quit(self) -> None:
        try:
            self.cmd("quit")
        except (QMPError, OSError):
            pass
        finally:
            self.sock.close()
