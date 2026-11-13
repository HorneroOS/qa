"""Contract tests for the Extensions 2.0 acceptance scenarios (qa#81).

These pin the *declared* matrix: coverage of every qa#81 dimension, honest
PENDING recording, and non-vacuous fixture preconditions. They execute no
guest and claim no scenario PASS; guest verdicts come only from run bundles
recorded in docs/SCENARIO-MATRIX.md.
"""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

import yaml

from hornero_qa.scenario import load

REPO = Path(__file__).resolve().parents[1]
SCENARIO_DIR = REPO / "scenarios" / "extensions"
ACCEPTANCE = REPO / "docs" / "EXTENSIONS-ACCEPTANCE.md"
TRIAGE = REPO / "docs" / "scenario-triage.yaml"

# Every qa#81 matrix dimension and Extensions 2.0 surface, mapped to the
# scenario(s) that must exist to cover it. Dimension -> scenario id suffixes.
COVERAGE: dict[str, tuple[str, ...]] = {
    "bar edge left": ("bar-edge-left",),
    "bar edge right": ("bar-edge-right",),
    "bar edge top": ("bar-edge-top",),
    "bar edge bottom": ("bar-edge-bottom",),
    "tooltip placement near every edge": (
        "bar-edge-left",
        "bar-edge-right",
        "bar-edge-top",
        "bar-edge-bottom",
    ),
    "popovers": ("bar-edge-left", "bar-edge-right", "bar-edge-top", "bar-edge-bottom"),
    "narrow displays": ("narrow-display",),
    "wide displays": ("hidpi-wide-display",),
    "HiDPI": ("hidpi-wide-display", "multimonitor-virtual"),
    "multi-monitor": ("multimonitor-virtual",),
    "themes": ("themes-reduced-motion",),
    "reduced motion": ("themes-reduced-motion",),
    "keyboard-only use": ("keyboard-only",),
    "offline/unavailable services": ("offline-unavailable-services",),
    "extension load errors": ("load-failure-isolation", "malformed-settings-resilience"),
    "all-dashboard-extensions-enabled stress": ("dashboard-all-enabled-stress",),
    "restart persistence": ("restart-persistence", "settings-persistence"),
    "disable cleanup": ("lifecycle-disable-enable",),
    "uninstall cleanup": ("uninstall-cleanup",),
    "PluginKit primitives": ("discovery-status", "themes-reduced-motion"),
    "settings UI": ("settings-persistence",),
    "dashboard layout": ("restart-persistence", "dashboard-all-enabled-stress", "keyboard-only"),
    "marketplace metadata": ("marketplace-metadata",),
    "safe mode/diagnostics": ("safe-mode-recovery", "load-failure-isolation"),
    "multi-surface plugins": ("multi-surface-loads",),
}

FOUNDATION_WAVE = (
    "discovery-status",
    "multi-surface-loads",
    "settings-persistence",
    "malformed-settings-resilience",
    "safe-mode-recovery",
    "load-failure-isolation",
    "lifecycle-disable-enable",
    "uninstall-cleanup",
    "restart-persistence",
    "marketplace-metadata",
    "offline-unavailable-services",
)


def _scenario_ids() -> list[str]:
    return sorted(p.stem for p in SCENARIO_DIR.glob("*.yaml"))


def _triage() -> dict[str, dict[str, str]]:
    data = yaml.safe_load(TRIAGE.read_text(encoding="utf-8"))
    scenarios: dict[str, dict[str, str]] = data["scenarios"]
    return scenarios


def test_every_qa81_dimension_has_a_scenario() -> None:
    ids = set(_scenario_ids())
    for dimension, suffixes in COVERAGE.items():
        for suffix in suffixes:
            assert suffix in ids, f"{dimension}: missing extensions/{suffix}"


def test_scenarios_are_valid_and_guard_qa81() -> None:
    for path in sorted(SCENARIO_DIR.glob("*.yaml")):
        sc = load(path)
        assert sc.id == f"extensions/{path.stem}"
        assert "qa#81" in sc.covers, f"{sc.id} does not declare covers qa#81"
        assert sc.proof, sc.id


def test_no_scenario_claims_a_pass_it_has_not_earned() -> None:
    for path in sorted(SCENARIO_DIR.glob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        assert "PENDING" in text, f"{path.name} does not record itself as PENDING"
        assert "EXECUTED" not in text, f"{path.name} claims an execution that has not happened"


def _probe_commands(path: Path) -> str:
    sc = load(path)
    runs: list[str] = []
    for item in [*sc.steps, *sc.proof]:
        probe = item.get("probe")
        if isinstance(probe, dict):
            runs.append(str(probe.get("run", "")))
            runs.append(str(probe.get("matches", "")))
    return "\n".join(runs)


def test_health_probes_are_not_vacuous_without_a_fixture() -> None:
    # "No failed extensions" must never be satisfiable by having zero
    # extensions installed: each scenario asserting failed == 0 must also
    # assert at least one loaded extension somewhere in its probes.
    for path in sorted(SCENARIO_DIR.glob("*.yaml")):
        commands = _probe_commands(path)
        if ".failed" not in commands:
            continue
        assert (
            "loaded >= 1" in commands or 'state == "loaded"' in commands or "([1-9][0-9]*) 0" in commands
        ), f"{path.name} can pass with no extension loaded"


def test_acceptance_doc_records_every_scenario_as_pending() -> None:
    doc = ACCEPTANCE.read_text(encoding="utf-8")
    for stem in _scenario_ids():
        row = f"`extensions/{stem}`"
        assert row in doc, f"acceptance matrix is missing {row}"
    pending_rows = sum(1 for line in doc.splitlines() if line.startswith("| `extensions/"))
    assert pending_rows == len(_scenario_ids())
    for line in doc.splitlines():
        if line.startswith("| `extensions/"):
            assert line.rstrip().endswith("| PENDING |"), line


def test_foundation_wave_is_named_in_the_acceptance_doc() -> None:
    doc = ACCEPTANCE.read_text(encoding="utf-8")
    for stem in FOUNDATION_WAVE:
        assert f"`extensions/{stem}`" in doc
    assert "Foundation wave" in doc
    assert "NOT TESTED" in doc
    assert "example-broken" in doc


def test_triage_records_every_scenario_pending_without_a_pass_claim() -> None:
    triage = _triage()
    for stem in _scenario_ids():
        entry = triage[f"extensions/{stem}"]
        assert entry["decision"] == "keep"
        assert "PENDING" in entry["schedule"], stem
        assert "EXECUTED" not in entry["schedule"], stem
        assert "no PASS is claimed" in entry["schedule"] or "No PASS is claimed" in entry["schedule"], stem


def test_probe_and_setup_commands_parse() -> None:
    # Guest probes are shell (often wrapping `python3 -c`): both layers must
    # at least parse, so a quoting bug is caught here instead of in the KVM
    # window. This executes nothing against a guest.
    for path in sorted(SCENARIO_DIR.glob("*.yaml")):
        sc = load(path)
        commands = list(sc.setup.get("commands") or [])
        for item in [*sc.steps, *sc.proof]:
            probe = item.get("probe")
            if isinstance(probe, dict) and probe.get("run"):
                commands.append(str(probe["run"]))
        for command in commands:
            checked = subprocess.run(
                ["bash", "-n"], input=command, text=True, capture_output=True, check=False
            )
            assert checked.returncode == 0, f"{path.name}: shell does not parse: {command!r}"
            for token in shlex.split(command):
                if (
                    token.startswith(("import ", "from "))
                    or "; print(" in token
                    or token.startswith("print(")
                ):
                    compile(token, f"{path.name}: probe python", "exec")


def test_multimonitor_scenario_claims_virtual_outputs_only() -> None:
    sc = load(SCENARIO_DIR / "multimonitor-virtual.yaml")
    assert "Virtual" in sc.text or "virtual" in sc.text
    assert "NOT TESTED" in sc.text
    assert sc.requires.get("outputs") == 2
