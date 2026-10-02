"""Result classes. Keep this small: humans and agents must classify alike."""

from __future__ import annotations

from enum import StrEnum


class Verdict(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"


class FailureClass(StrEnum):
    """Who is to blame. `PRODUCT*` are Hornero regressions; the rest are not."""

    PRODUCT = "product"  # proof failed, guest healthy
    PRODUCT_CRASH = "product_crash"  # compositor or shell process died
    DRIVER = "driver"  # agentic driver/model failure (malformed output, gave up)
    HARNESS = "harness"  # Hornero QA itself failed
    PROVISIONING = "provisioning"  # image/composition could not be prepared
    BOOT = "boot"  # guest never reached a desktop
    TIMEOUT = "timeout"  # wall budget exceeded without a verdict
    INCONCLUSIVE = "inconclusive"  # evidence insufficient


PRODUCT_CLASSES = frozenset({FailureClass.PRODUCT, FailureClass.PRODUCT_CRASH})


def is_regression(cls: FailureClass | None) -> bool:
    """Only product classes count against Hornero."""
    return cls in PRODUCT_CLASSES


class QAError(Exception):
    """An error with a known failure class."""

    def __init__(self, cls: FailureClass, message: str) -> None:
        super().__init__(message)
        self.cls = cls
