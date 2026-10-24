from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from typing import Any

import yaml
from PIL import Image

from hornero_qa.cli import main
from hornero_qa.studio_gate import evaluate


def _manifest() -> dict[str, Any]:
    return {
        "schema": "hornero.qa.studio-acceptance/1",
        "edition_state": "planned",
        "items": [
            {
                "id": "audio",
                "outcome": "Audio workflow evidence is accepted.",
                "required": True,
                "condition": "always",
                "enabled": None,
                "owner_issues": ["qa#21"],
                "evidence_kind": "bundle",
                "fixture": {
                    "id": None,
                    "approved": False,
                    "notes": "Owner selection required.",
                    "sha256": None,
                },
                "status": "pending",
                "evidence": [],
                "review": {"decision": "pending", "reference": None},
            }
        ],
    }


def _accepted_run(runs_dir: Path, tmp_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    scenario = (
        "id: studio/audio\npurpose: Test audio evidence.\n"
        "instruction: Inspect audio.\nproof:\n"
        "  - note: Check the declared audio probe.\n"
        '    probe: {run: "test -e /tmp/audio-ready", equals: ""}\n'
    )
    scenario_path = tmp_path / "scenario.yaml"
    scenario_path.write_text(scenario, encoding="utf-8")
    pins = {
        "shell_sha": "a" * 40,
        "config_sha": "b" * 40,
        "horneroctl_sha256": "c" * 64,
        "guest_sha": "d" * 40,
        "iso_sha256": "e" * 64,
        "manifest_sha256": "f" * 64,
        "catalogue_sha256": "1" * 64,
        "hardware_fixture": "qemu-audio-v1",
        "hardware_fixture_sha256": "2" * 64,
    }
    bundle = runs_dir / "run-1"
    (bundle / "screenshots").mkdir(parents=True)
    (bundle / "logs").mkdir()
    output = io.BytesIO()
    Image.new("RGB", (1, 1)).save(output, format="PNG")
    png = output.getvalue()
    shot = bundle / "screenshots/frame.png"
    shot.write_bytes(png)
    (bundle / "logs/pw-dump.txt").write_text("fixture log", encoding="utf-8")
    (bundle / "scenario.yaml").write_text(scenario, encoding="utf-8")
    (bundle / "actions.jsonl").write_text('{"t":0.1,"kind":"observe"}\n', encoding="utf-8")
    (bundle / "assertions.json").write_text(
        '[{"kind":"probe","where":"proof 0","ok":true,"detail":"healthy"}]\n', encoding="utf-8"
    )
    product = pins.copy()
    (bundle / "run.json").write_text(
        json.dumps(
            {
                "schema": "hornero.qa.run/1",
                "run_id": "run-1",
                "scenario": "studio/audio",
                "started": "2026-10-24T00:00:00Z",
                "product": product,
                "environment": {},
                "catalogues": {},
            }
        ),
        encoding="utf-8",
    )
    (shot.with_suffix(".json")).write_text(
        json.dumps(
            {
                "schema": "hornero.qa.screenshot/1",
                "file": shot.name,
                "sha256": hashlib.sha256(png).hexdigest(),
                "run_id": "run-1",
                "scenario": "studio/audio",
                "product": product,
            }
        ),
        encoding="utf-8",
    )
    (bundle / "result.json").write_text(
        json.dumps({"run_id": "run-1", "verdict": "pass", "finished": "2026-10-24T00:01:00Z"}),
        encoding="utf-8",
    )
    evidence = {
        "kind": "bundle",
        "run_id": "run-1",
        "scenario": "studio/audio",
        "scenario_sha256": hashlib.sha256(scenario.encode()).hexdigest(),
        "pins": pins,
    }
    return evidence, pins


def test_pending_or_unsupported_outcome_blocks_preview(tmp_path: Path) -> None:
    manifest = tmp_path / "acceptance.yaml"
    manifest.write_text(yaml.safe_dump(_manifest()), encoding="utf-8")

    report = evaluate(manifest, tmp_path / "runs")

    assert report["eligible_for_owner_review"] is False
    assert report["recommendation"] == "blocked"
    assert "no evidence is indexed" in report["items"][0]["blocking_reasons"]

    data = _manifest()
    data["items"][0]["status"] = "unsupported"
    manifest.write_text(yaml.safe_dump(data), encoding="utf-8")
    assert evaluate(manifest, tmp_path / "runs")["recommendation"] == "blocked"


def test_studio_gate_accepts_only_complete_pinned_reviewed_evidence(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    evidence, _ = _accepted_run(runs_dir, tmp_path)
    data = _manifest()
    data["items"][0] |= {
        "fixture": {
            "id": "qemu-audio-v1",
            "approved": True,
            "sha256": "2" * 64,
            "notes": "Reviewed fixture.",
        },
        "status": "accepted",
        "evidence": [evidence],
        "review": {"decision": "accepted", "reference": "https://github.com/HorneroOS/qa/pull/99"},
    }
    manifest = tmp_path / "acceptance.yaml"
    manifest.write_text(yaml.safe_dump(data), encoding="utf-8")

    report = evaluate(manifest, runs_dir)

    assert report["eligible_for_owner_review"] is True
    assert report["recommendation"] == "ready_for_owner_review"


def test_stale_scenario_and_hardware_provenance_block_evidence(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    evidence, _ = _accepted_run(runs_dir, tmp_path)
    data = _manifest()
    data["items"][0] |= {
        "fixture": {
            "id": "qemu-audio-v1",
            "approved": True,
            "sha256": "2" * 64,
            "notes": "Reviewed fixture.",
        },
        "status": "accepted",
        "evidence": [evidence],
        "review": {"decision": "accepted", "reference": "https://github.com/HorneroOS/qa/pull/99"},
    }
    data["items"][0]["evidence"][0]["scenario_sha256"] = "0" * 64
    data["items"][0]["evidence"][0]["pins"]["hardware_fixture"] = "different-fixture"
    manifest = tmp_path / "acceptance.yaml"
    manifest.write_text(yaml.safe_dump(data), encoding="utf-8")

    report = evaluate(manifest, runs_dir)

    assert report["eligible_for_owner_review"] is False
    reasons = report["items"][0]["blocking_reasons"]
    assert "bundle 'run-1' uses a stale scenario revision" in reasons


def test_wrong_hardware_fixture_blocks_otherwise_current_bundle(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    evidence, _ = _accepted_run(runs_dir, tmp_path)
    data = _manifest()
    data["items"][0] |= {
        "fixture": {
            "id": "qemu-audio-v1",
            "approved": True,
            "sha256": "2" * 64,
            "notes": "Reviewed fixture.",
        },
        "status": "accepted",
        "evidence": [evidence],
        "review": {"decision": "accepted", "reference": "https://github.com/HorneroOS/qa/pull/99"},
    }
    data["items"][0]["evidence"][0]["pins"]["hardware_fixture"] = "different-fixture"
    manifest = tmp_path / "acceptance.yaml"
    manifest.write_text(yaml.safe_dump(data), encoding="utf-8")

    report = evaluate(manifest, runs_dir)

    assert report["eligible_for_owner_review"] is False
    assert any("hardware_fixture" in reason for reason in report["items"][0]["blocking_reasons"])


def test_approved_fixture_mismatch_blocks_even_when_run_and_evidence_agree(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    evidence, _ = _accepted_run(runs_dir, tmp_path)
    data = _manifest()
    data["items"][0] |= {
        "fixture": {"id": "approved-fixture", "approved": True, "sha256": "3" * 64, "notes": "Approved."},
        "status": "accepted",
        "evidence": [evidence],
        "review": {"decision": "accepted", "reference": "https://github.com/HorneroOS/qa/pull/99"},
    }
    manifest = tmp_path / "acceptance.yaml"
    manifest.write_text(yaml.safe_dump(data), encoding="utf-8")

    report = evaluate(manifest, runs_dir)

    assert report["recommendation"] == "blocked"
    assert any(
        "owner-approved hardware fixture" in reason for reason in report["items"][0]["blocking_reasons"]
    )


def test_invalid_screenshot_bytes_and_non_pr_review_link_block(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    evidence, _ = _accepted_run(runs_dir, tmp_path)
    data = _manifest()
    data["items"][0] |= {
        "fixture": {"id": "qemu-audio-v1", "approved": True, "sha256": "2" * 64, "notes": "Reviewed."},
        "status": "accepted",
        "evidence": [evidence],
        "review": {"decision": "accepted", "reference": "https://github.com/HorneroOS/qa/issues/99"},
    }
    (runs_dir / "run-1/screenshots/frame.png").write_bytes(b"not a PNG")
    manifest = tmp_path / "acceptance.yaml"
    manifest.write_text(yaml.safe_dump(data), encoding="utf-8")

    report = evaluate(manifest, runs_dir)

    reasons = report["items"][0]["blocking_reasons"]
    assert any("not a valid PNG" in reason for reason in reasons)
    assert any("pull request" in reason for reason in reasons)


def test_failed_assertion_cannot_be_hidden_by_pass_result(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    evidence, _ = _accepted_run(runs_dir, tmp_path)
    data = _manifest()
    data["items"][0] |= {
        "fixture": {"id": "qemu-audio-v1", "approved": True, "sha256": "2" * 64, "notes": "Reviewed."},
        "status": "accepted",
        "evidence": [evidence],
        "review": {"decision": "accepted", "reference": "https://github.com/HorneroOS/qa/pull/99"},
    }
    (runs_dir / "run-1/assertions.json").write_text(
        '[{"kind":"probe","where":"audio","ok":false,"detail":"device absent"}]\n',
        encoding="utf-8",
    )
    manifest = tmp_path / "acceptance.yaml"
    manifest.write_text(yaml.safe_dump(data), encoding="utf-8")

    report = evaluate(manifest, runs_dir)

    assert report["recommendation"] == "blocked"
    assert any("failed assertion" in reason for reason in report["items"][0]["blocking_reasons"])


def test_bundle_must_record_each_scenario_proof_check(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    evidence, _ = _accepted_run(runs_dir, tmp_path)
    data = _manifest()
    data["items"][0] |= {
        "fixture": {"id": "qemu-audio-v1", "approved": True, "sha256": "2" * 64, "notes": "Reviewed."},
        "status": "accepted",
        "evidence": [evidence],
        "review": {"decision": "accepted", "reference": "https://github.com/HorneroOS/qa/pull/99"},
    }
    (runs_dir / "run-1/assertions.json").write_text(
        '[{"kind":"probe","where":"unrelated check","ok":true,"detail":"healthy"}]\n',
        encoding="utf-8",
    )
    manifest = tmp_path / "acceptance.yaml"
    manifest.write_text(yaml.safe_dump(data), encoding="utf-8")

    report = evaluate(manifest, runs_dir)

    assert report["recommendation"] == "blocked"
    assert any("do not cover" in reason for reason in report["items"][0]["blocking_reasons"])


def test_cli_reports_current_studio_gate_as_blocked(capsys: Any, tmp_path: Path) -> None:
    manifest = Path(__file__).parents[1] / "docs/studio-acceptance.yaml"

    code = main(["studio-gate", "--manifest", str(manifest), "--runs-dir", str(tmp_path / "runs")])

    assert code == 1
    assert "Studio Preview recommendation blocked" in capsys.readouterr().out


def test_documentation_review_is_not_misrepresented_as_vm_execution(tmp_path: Path) -> None:
    data = _manifest()
    item = data["items"][0]
    item |= {
        "evidence_kind": "review",
        "fixture": {"id": "studio-doc-review", "approved": True, "sha256": None, "notes": "Review fixture."},
        "status": "accepted",
        "evidence": [{"kind": "review", "reference": "https://github.com/HorneroOS/docs/pull/80"}],
        "review": {"decision": "accepted", "reference": "https://github.com/HorneroOS/docs/pull/80"},
    }
    manifest = tmp_path / "acceptance.yaml"
    manifest.write_text(yaml.safe_dump(data), encoding="utf-8")

    report = evaluate(manifest, tmp_path / "runs")

    assert report["eligible_for_owner_review"] is True


def test_conditional_companion_gate_blocks_until_applicability_is_reviewed(tmp_path: Path) -> None:
    data = _manifest()
    item = data["items"][0]
    item["required"] = False
    item["condition"] = "when-enabled"
    item["enabled"] = None
    manifest = tmp_path / "acceptance.yaml"
    manifest.write_text(yaml.safe_dump(data), encoding="utf-8")

    report = evaluate(manifest, tmp_path / "runs")

    assert report["recommendation"] == "blocked"
    assert "conditional applicability is unresolved" in report["items"][0]["blocking_reasons"]
