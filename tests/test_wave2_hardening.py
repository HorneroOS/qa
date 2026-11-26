"""Unit tests for Wave 2 QA hardening (#99, #100, #101, #102)."""

from __future__ import annotations

import json
import subprocess
from datetime import date
from pathlib import Path

import pytest

from hornero_qa.engines.install import InstallEngine
from hornero_qa.engines.native import NativeEngine, ProbeResult
from hornero_qa.matrix import (
    ARTIFACT_DIGESTS_SCHEMA,
    MatrixError,
    expired_quarantines,
    generate_matrix,
    stale_scenarios,
)
from hornero_qa.runner import _probe_ok
from hornero_qa.scenario import REPO_ROOT, load
from hornero_qa.state import QAState
from hornero_qa.studio_gate import StudioGateError, _load_artifact_digests
from hornero_qa.vision import contrast_ratio, relative_luminance
from hornero_qa.web import DEFAULT_BASE, _truth

SHA_A = "a" * 64
SHA_B = "b" * 64


# ------------------------------------------------------------------ #99 --
def _init_git_repo(repo: Path) -> None:
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "qa@test"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "QA"], check=True)


def _git_add_all(repo: Path) -> None:
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)


def test_matrix_accepts_artifact_digests_manifest(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "scenarios" / "demo").mkdir(parents=True)
    (repo / "docs").mkdir(parents=True)
    scenario_yaml = (
        "id: demo/one\n"
        "purpose: Verify content-addressed artifact manifest.\n"
        "instruction: Boot and check.\n"
        "proof:\n"
        "  - probe: {run: 'true'}\n"
    )
    (repo / "scenarios" / "demo" / "one.yaml").write_text(scenario_yaml, encoding="utf-8")
    (repo / "docs" / "scenario-triage.yaml").write_text(
        "scenarios:\n  demo/one:\n    decision: keep\n    rationale: Core check\n    schedule: per-PR\n",
        encoding="utf-8",
    )
    bundle = repo / "docs" / "evidence" / "runs" / "20261126T000000Z-demo-one-1"
    bundle.mkdir(parents=True)
    (bundle / "scenario.yaml").write_text(scenario_yaml, encoding="utf-8")
    (bundle / "run.json").write_text(
        json.dumps(
            {
                "schema": "hornero.qa.run/1",
                "run_id": "20261126T000000Z-demo-one-1",
                "scenario": "demo/one",
                "started": "2026-11-26T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    (bundle / "result.json").write_text(
        json.dumps(
            {
                "run_id": "20261126T000000Z-demo-one-1",
                "finished": "2026-11-26T00:01:00Z",
                "verdict": "pass",
            }
        ),
        encoding="utf-8",
    )
    (bundle / "actions.jsonl").write_text('{"kind":"ready"}\n', encoding="utf-8")
    (bundle / "assertions.json").write_text("[]", encoding="utf-8")
    (bundle / "artifact_digests.json").write_text(
        json.dumps(
            {
                "schema": ARTIFACT_DIGESTS_SCHEMA,
                "artifacts": {
                    "screenshots/001-desktop.png": {
                        "sha256": SHA_A,
                        "url": "https://r2.horneroos.com/qa/001-desktop.png",
                    },
                    "logs/serial.log": {
                        "sha256": SHA_B,
                        "url": "s3://hornero-qa/logs/serial.log",
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    _init_git_repo(repo)
    _git_add_all(repo)

    matrix_md = generate_matrix(repo, Path("docs/evidence/runs"))
    assert "| `demo/one` | 2026-11-26 | PASS |" in matrix_md


def test_studio_gate_load_artifact_digests_validation(tmp_path: Path) -> None:
    good = tmp_path / "good"
    good.mkdir()
    (good / "artifact_digests.json").write_text(
        json.dumps(
            {
                "schema": ARTIFACT_DIGESTS_SCHEMA,
                "artifacts": {
                    "screenshots/shot.png": {"sha256": SHA_A, "url": "r2://bucket/shot.png"},
                    "logs/serial.log": {"sha256": SHA_B, "url": "https://r2.horneroos.com/serial.log"},
                },
            }
        ),
        encoding="utf-8",
    )
    loaded = _load_artifact_digests(good)
    assert loaded is not None
    assert "screenshots/shot.png" in loaded

    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "artifact_digests.json").write_text(
        json.dumps(
            {
                "schema": ARTIFACT_DIGESTS_SCHEMA,
                "artifacts": {"screenshots/shot.png": {"sha256": "not-hex", "url": "http://insecure"}},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(StudioGateError):
        _load_artifact_digests(bad)


# ----------------------------------------------------------------- #100 --
def test_native_engine_niri_is_headless_without_host_hyprctl() -> None:
    assert not hasattr(NativeEngine, "_find_host_display_client")


def test_install_engine_argv_serial_and_detach_reboot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = QAState(root=tmp_path / "state")
    iso = tmp_path / "hornero.iso"
    iso.write_bytes(b"fake-iso")
    run_dir = tmp_path / "run"
    engine = InstallEngine(state=state, iso=iso, run_dir=run_dir, disk_gb=16, mem_mb=4096)

    with_iso = engine.build_qemu_argv(attach_iso=True)
    assert any(f"file={iso},media=cdrom" in arg for arg in with_iso)
    assert "order=dc" in with_iso

    without_iso = engine.build_qemu_argv(attach_iso=False)
    assert not any("media=cdrom" in arg for arg in without_iso)
    assert "order=c" in without_iso

    events: list[str] = []

    def fake_stop(*, keep_disk: bool = False) -> None:
        events.append(f"stop:keep_disk={keep_disk}")
        engine.iso_attached = False

    def fake_start(*, attach_iso: bool = True) -> None:
        events.append(f"start:attach_iso={attach_iso}")
        engine.iso_attached = attach_iso
        engine.serial.parent.mkdir(parents=True, exist_ok=True)
        engine.serial.write_text("booting...\nhornero login:\n", encoding="utf-8")

    monkeypatch.setattr(engine, "stop", fake_stop)
    monkeypatch.setattr(engine, "start", fake_start)
    monkeypatch.setattr(engine, "alive", lambda: True)

    assert engine.detach_iso_and_reboot(ready_marker="login:", timeout_s=2.0, poll_s=0.01) is True
    assert events == ["stop:keep_disk=True", "start:attach_iso=False"]
    assert engine.iso_attached is False


# ----------------------------------------------------------------- #101 --
def test_web_default_base_and_signed_download_validation() -> None:
    assert DEFAULT_BASE == "https://horneroos.com"

    class _FakePage:
        def __init__(self, hrefs: list[str]) -> None:
            self._hrefs = hrefs

        def goto(self, _url: str, wait_until: str = "load") -> None:
            pass

        def eval_on_selector_all(self, _sel: str, _expr: str) -> list[str]:
            return self._hrefs

    ok, _ = _truth(
        "no_download_claims",
        _FakePage(
            [
                "https://github.com/HorneroOS/hornero/releases/download/v0.1/hornero.iso",
                "https://github.com/HorneroOS/hornero/releases/download/v0.1/hornero.iso.sha256",
            ]
        ),  # type: ignore[arg-type]
        DEFAULT_BASE,
    )
    assert ok is True

    bad_no_sig, _ = _truth(
        "no_download_claims",
        _FakePage(["https://github.com/HorneroOS/hornero/releases/download/v0.1/hornero.iso"]),  # type: ignore[arg-type]
        DEFAULT_BASE,
    )
    assert bad_no_sig is False

    bad_http, _ = _truth(
        "no_download_claims",
        _FakePage(
            [
                "http://horneroos.com/hornero.iso",
                "https://horneroos.com/hornero.iso.sha256",
            ]
        ),  # type: ignore[arg-type]
        DEFAULT_BASE,
    )
    assert bad_http is False


def test_matrix_quarantine_expiry_fails_staleness(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "scenarios" / "demo").mkdir(parents=True)
    (repo / "docs").mkdir(parents=True)
    (repo / "scenarios" / "demo" / "quarantined.yaml").write_text(
        "id: demo/quarantined\n"
        "purpose: Quarantined scenario.\n"
        "instruction: Run the check.\n"
        "proof:\n"
        "  - probe: {run: 'true'}\n",
        encoding="utf-8",
    )
    (repo / "docs" / "scenario-triage.yaml").write_text(
        "scenarios:\n"
        "  demo/quarantined:\n"
        "    decision: fix\n"
        "    rationale: Waiting on upstream fix\n"
        "    expires: '2026-11-01'\n",
        encoding="utf-8",
    )
    _init_git_repo(repo)
    _git_add_all(repo)

    expired = expired_quarantines(repo, Path("docs/evidence/runs"), today=date(2026, 11, 26))
    assert len(expired) == 1
    assert expired[0][0] == "demo/quarantined"

    stale = stale_scenarios(repo, Path("docs/evidence/runs"), max_age_days=30, today=date(2026, 11, 26))
    assert stale == [("demo/quarantined", "2026-11-01", "Quarantine expired (2026-11-01)")]

    # Invalid expires date raises MatrixError
    (repo / "docs" / "scenario-triage.yaml").write_text(
        "scenarios:\n"
        "  demo/quarantined:\n"
        "    decision: fix\n"
        "    rationale: Bad date\n"
        "    expires: 'not-a-date'\n",
        encoding="utf-8",
    )
    with pytest.raises(MatrixError):
        expired_quarantines(repo, Path("docs/evidence/runs"), today=date(2026, 11, 26))


def test_wcag_contrast_ratio() -> None:
    assert relative_luminance((0, 0, 0)) == pytest.approx(0.0)
    assert relative_luminance((255, 255, 255)) == pytest.approx(1.0)
    assert contrast_ratio((255, 255, 255), (0, 0, 0)) == pytest.approx(21.0)
    assert contrast_ratio((0, 0, 0), (255, 255, 255)) == pytest.approx(21.0)
    assert contrast_ratio((120, 120, 120), (120, 120, 120)) == pytest.approx(1.0)
    # WCAG AA normal text threshold >= 4.5 for dark gray on white
    assert contrast_ratio((89, 89, 89), (255, 255, 255)) >= 4.5


# ----------------------------------------------------------------- #102 --
def test_perf_baseline_budget_assertions() -> None:
    sc = load(REPO_ROOT / "scenarios" / "perf" / "baseline.yaml")
    assert sc.id == "perf/baseline"

    ok, _ = _probe_ok(
        {"run": "perf", "json": "samples.0.rss_kb", "max_rss_kb": 200000},
        ProbeResult(0, json.dumps({"samples": [{"rss_kb": 150000}]}), ""),
    )
    assert ok is True

    fail, why = _probe_ok(
        {"run": "perf", "json": "samples.0.rss_kb", "max_rss_kb": 100000},
        ProbeResult(0, json.dumps({"samples": [{"rss_kb": 150000}]}), ""),
    )
    assert fail is False
    assert "exceeds budget" in why

    ok_cs, _ = _probe_ok(
        {"run": "perf", "max_cold_start_ms": 1500},
        ProbeResult(0, json.dumps({"cold_start_ms": 950}), ""),
    )
    assert ok_cs is True

    fail_cs, why_cs = _probe_ok(
        {"run": "perf", "max_cold_start_ms": 800},
        ProbeResult(0, json.dumps({"cold_start_ms": 950}), ""),
    )
    assert fail_cs is False
    assert "cold_start_ms" in why_cs
