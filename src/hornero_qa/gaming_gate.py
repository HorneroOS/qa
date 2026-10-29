"""Fail-closed Gaming acceptance gate; never changes product maturity.

Reuses the Studio gate's evidence verification (bundle digests, pins,
screenshot provenance, review links) with the Gaming schema and label.
Physical-hardware items stay blocked until real fixtures are approved:
VM evidence is never hardware evidence.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hornero_qa.studio_gate import evaluate as _evaluate

SCHEMA_PATH = Path(__file__).parent / "schemas" / "gaming_acceptance.schema.json"


def evaluate(manifest_path: Path, runs_dir: Path) -> dict[str, Any]:
    return _evaluate(manifest_path, runs_dir, schema_path=SCHEMA_PATH, label="Gaming")
