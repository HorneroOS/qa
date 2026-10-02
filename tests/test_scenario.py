from __future__ import annotations

from pathlib import Path

import pytest

from hornero_qa.scenario import SCENARIO_DIR, ScenarioError, discover, load, parse

MINIMAL = """
id: smoke/x
purpose: A minimal scenario used by unit tests.
instruction: Do nothing.
proof:
  - probe: {run: "true"}
"""


def test_minimal_defaults() -> None:
    sc = parse(MINIMAL)
    assert sc.wall_s == 180 and sc.max_actions == 60 and sc.max_malformed == 3
    assert sc.resolution == (1280, 800) and sc.outputs == 1


@pytest.mark.parametrize(
    ("patch", "where"),
    [
        ("proof: []", "proof"),
        ("steps: [{key: a, type: b}]", "steps/0"),
        ("steps: [{pause: 9}]", "steps/0/pause"),
        ("covers: [not-an-issue]", "covers/0"),
        ("requires: {outputs: 5}", "requires/outputs"),
        ("bogus: 1", "<root>"),
    ],
)
def test_schema_rejects(patch: str, where: str) -> None:
    key = patch.split(":")[0]
    text = "\n".join(ln for ln in MINIMAL.splitlines() if not ln.startswith(f"{key}:"))
    if key == "proof":
        text = text.replace('  - probe: {run: "true"}', "")
    with pytest.raises(ScenarioError, match=where):
        parse(text + "\n" + patch + "\n")


def test_id_must_match_path(tmp_path: Path) -> None:
    sub = SCENARIO_DIR / "smoke"
    p = sub / "desktop-ready.yaml"
    assert load(p).id == "smoke/desktop-ready"
    with pytest.raises(ScenarioError, match="must match its path"):
        parse(MINIMAL, source=sub / "other.yaml")


def test_repository_scenarios_are_valid() -> None:
    paths = discover()
    assert paths, "no scenarios found"
    for p in paths:
        sc = load(p)
        assert sc.proof, p
