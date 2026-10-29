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

# Gate contract (docs/GAMING-ACCEPTANCE.md): these items can never be
# removed or demoted by a custom manifest.
MANDATORY_IDS = frozenset(
    {
        "clean-install-first-boot",
        "selection-parity",
        "gaming-doctor-contract",
        "graphics-topology-fixtures",
        "steam-proton-gameplay",
        "controller-handheld-session",
        "graphics-update-recovery",
        "anti-cheat-honesty",
    }
)

# These items are meaningless with a virtual fixture.
PHYSICAL_IDS = frozenset(
    {
        "graphics-topology-fixtures",
        "steam-proton-gameplay",
        "controller-handheld-session",
    }
)


def evaluate(manifest_path: Path, runs_dir: Path) -> dict[str, Any]:
    return _evaluate(
        manifest_path,
        runs_dir,
        schema_path=SCHEMA_PATH,
        label="Gaming",
        mandatory_ids=MANDATORY_IDS,
        physical_ids=PHYSICAL_IDS,
    )
