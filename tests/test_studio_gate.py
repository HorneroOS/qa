from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from PIL import Image

from hornero_qa.cli import main
from hornero_qa.studio_gate import StudioGateError, bundle_digest, evaluate


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
                    "manifest": None,
                },
                "status": "pending",
                "evidence": [],
                "review": {"decision": "pending", "reference": None},
            }
        ],
    }


def _approved_fixture(tmp_path: Path, fixture_id: str = "qemu-audio-v1") -> dict[str, Any]:
    path = tmp_path / "fixtures/audio.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    contents = (
        "schema: hornero.qa.studio-fixture/1\n"
        f"id: {fixture_id}\n"
        "kind: virtual\n"
        "hardware: {audio: qemu-virtual}\n"
        "software: {kernel: pinned, pipewire: pinned}\n"
    )
    path.write_text(contents, encoding="utf-8")
    return {
        "id": fixture_id,
        "approved": True,
        "sha256": hashlib.sha256(contents.encode()).hexdigest(),
        "manifest": "fixtures/audio.yaml",
        "notes": "Reviewed fixture.",
    }


def _accepted_run(runs_dir: Path, tmp_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    scenario = (
        "id: studio/audio\npurpose: Test audio evidence.\n"
        "instruction: Inspect audio.\nproof:\n"
        "  - note: Check the declared audio probe.\n"
        '    probe: {run: "test -e /tmp/audio-ready", equals: ""}\n'
        "  - note: Check the second declared audio probe.\n"
        '    probe: {run: "test -d /tmp/audio-ready", equals: ""}\n'
    )
    scenario_path = tmp_path / "scenario.yaml"
    scenario_path.write_text(scenario, encoding="utf-8")
    fixture = _approved_fixture(tmp_path)
    pins = {
        "shell_sha": "a" * 40,
        "config_sha": "b" * 40,
        "horneroctl_sha256": "c" * 64,
        "image_sha256": "3" * 64,
        "guest_sha": "d" * 40,
        "iso_sha256": "e" * 64,
        "manifest_sha256": "f" * 64,
        "catalogue_sha256": "1" * 64,
        "hardware_fixture": "qemu-audio-v1",
        "hardware_fixture_sha256": fixture["sha256"],
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
        '[{"kind":"probe","where":"proof 0","ok":true,"detail":"ready"},'
        '{"kind":"probe","where":"proof 1","ok":true,"detail":"available"}]\n',
        encoding="utf-8",
    )
    product = pins.copy()
    (bundle / "run.json").write_text(
        json.dumps(
            {
                "schema": "hornero.qa.run/1",
                "run_id": "run-1",
                "scenario": "studio/audio",
                "started": "2026-10-24T00:00:00Z",
                "image_sha256": pins["image_sha256"],
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
        "bundle_sha256": bundle_digest(bundle),
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


@pytest.mark.parametrize(
    "text",
    [
        "schema: hornero.qa.studio-acceptance/1\nedition_state: planned\nitems: []\nitems: []\n",
        "schema: hornero.qa.studio-acceptance/1\nedition_state: planned\nitems:\n"
        "  - id: audio\n    required: true\n    required: false\n",
    ],
)
def test_duplicate_manifest_keys_are_rejected(tmp_path: Path, text: str) -> None:
    manifest = tmp_path / "acceptance.yaml"
    manifest.write_text(text, encoding="utf-8")

    with pytest.raises(StudioGateError, match="duplicate key"):
        evaluate(manifest, tmp_path / "runs")


def test_studio_gate_accepts_only_complete_pinned_reviewed_evidence(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    evidence, _ = _accepted_run(runs_dir, tmp_path)
    data = _manifest()
    data["items"][0] |= {
        "fixture": _approved_fixture(tmp_path),
        "status": "accepted",
        "evidence": [evidence],
        "review": {"decision": "accepted", "reference": "https://github.com/HorneroOS/qa/pull/99"},
    }
    manifest = tmp_path / "acceptance.yaml"
    manifest.write_text(yaml.safe_dump(data), encoding="utf-8")

    report = evaluate(manifest, runs_dir)

    assert report["eligible_for_owner_review"] is True
    assert report["recommendation"] == "ready_for_owner_review"


def test_bundle_content_change_after_review_blocks_evidence(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    evidence, _ = _accepted_run(runs_dir, tmp_path)
    data = _manifest()
    data["items"][0] |= {
        "fixture": _approved_fixture(tmp_path),
        "status": "accepted",
        "evidence": [evidence],
        "review": {"decision": "accepted", "reference": "https://github.com/HorneroOS/qa/pull/99"},
    }
    (runs_dir / "run-1/logs/pw-dump.txt").write_text("changed after review", encoding="utf-8")
    manifest = tmp_path / "acceptance.yaml"
    manifest.write_text(yaml.safe_dump(data), encoding="utf-8")

    report = evaluate(manifest, runs_dir)

    assert report["recommendation"] == "blocked"
    assert any("content SHA256 does not match" in reason for reason in report["items"][0]["blocking_reasons"])


def test_bundle_evidence_requires_content_digest(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    evidence, _ = _accepted_run(runs_dir, tmp_path)
    del evidence["bundle_sha256"]
    data = _manifest()
    data["items"][0] |= {
        "fixture": _approved_fixture(tmp_path),
        "status": "accepted",
        "evidence": [evidence],
        "review": {"decision": "accepted", "reference": "https://github.com/HorneroOS/qa/pull/99"},
    }
    manifest = tmp_path / "acceptance.yaml"
    manifest.write_text(yaml.safe_dump(data), encoding="utf-8")

    with pytest.raises(StudioGateError, match="not valid under any of the given schemas"):
        evaluate(manifest, runs_dir)


def test_bundle_digest_rejects_symlinks(tmp_path: Path) -> None:
    bundle = tmp_path / "run-1"
    bundle.mkdir()
    outside = tmp_path / "outside.log"
    outside.write_text("private", encoding="utf-8")
    (bundle / "leak.log").symlink_to(outside)

    with pytest.raises(StudioGateError, match="bundle contains a symlink"):
        bundle_digest(bundle)


def test_cli_bundle_digest_rejects_traversal(tmp_path: Path, capsys: Any) -> None:
    code = main(["studio-gate", "--runs-dir", str(tmp_path), "--bundle-digest", "../outside"])

    assert code == 1
    assert "invalid bundle ID" in capsys.readouterr().err


def test_cli_prints_bundle_digest_for_acceptance_index(tmp_path: Path, capsys: Any) -> None:
    runs_dir = tmp_path / "runs"
    evidence, _ = _accepted_run(runs_dir, tmp_path)

    code = main(["studio-gate", "--runs-dir", str(runs_dir), "--bundle-digest", "run-1"])

    assert code == 0
    assert capsys.readouterr().out.strip() == evidence["bundle_sha256"]


def test_stale_scenario_and_hardware_provenance_block_evidence(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    evidence, _ = _accepted_run(runs_dir, tmp_path)
    data = _manifest()
    data["items"][0] |= {
        "fixture": _approved_fixture(tmp_path),
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
        "fixture": _approved_fixture(tmp_path),
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


def test_changed_image_digest_blocks_otherwise_current_bundle(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    evidence, _ = _accepted_run(runs_dir, tmp_path)
    data = _manifest()
    data["items"][0] |= {
        "fixture": _approved_fixture(tmp_path),
        "status": "accepted",
        "evidence": [evidence],
        "review": {"decision": "accepted", "reference": "https://github.com/HorneroOS/qa/pull/99"},
    }
    data["items"][0]["evidence"][0]["pins"]["image_sha256"] = "4" * 64
    manifest = tmp_path / "acceptance.yaml"
    manifest.write_text(yaml.safe_dump(data), encoding="utf-8")

    report = evaluate(manifest, runs_dir)

    assert report["recommendation"] == "blocked"
    assert any("image_sha256" in reason for reason in report["items"][0]["blocking_reasons"])


def test_approved_fixture_mismatch_blocks_even_when_run_and_evidence_agree(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    evidence, _ = _accepted_run(runs_dir, tmp_path)
    data = _manifest()
    data["items"][0] |= {
        "fixture": _approved_fixture(tmp_path, "approved-fixture"),
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


def test_fixture_manifest_content_must_match_approved_digest(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    evidence, _ = _accepted_run(runs_dir, tmp_path)
    fixture = _approved_fixture(tmp_path)
    (tmp_path / fixture["manifest"]).write_text(
        "schema: hornero.qa.studio-fixture/1\nid: qemu-audio-v1\nkind: virtual\n"
        "hardware: {audio: changed}\nsoftware: {kernel: pinned, pipewire: pinned}\n",
        encoding="utf-8",
    )
    data = _manifest()
    data["items"][0] |= {
        "fixture": fixture,
        "status": "accepted",
        "evidence": [evidence],
        "review": {"decision": "accepted", "reference": "https://github.com/HorneroOS/qa/pull/99"},
    }
    manifest = tmp_path / "acceptance.yaml"
    manifest.write_text(yaml.safe_dump(data), encoding="utf-8")

    report = evaluate(manifest, runs_dir)

    assert report["recommendation"] == "blocked"
    assert any("SHA256 does not match" in reason for reason in report["items"][0]["blocking_reasons"])


def test_fixture_manifest_rejects_symlinked_parent_directory(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    evidence, _ = _accepted_run(runs_dir, tmp_path)
    fixture = _approved_fixture(tmp_path)
    (tmp_path / "fixtures").rename(tmp_path / "actual-fixtures")
    (tmp_path / "fixtures").symlink_to("actual-fixtures", target_is_directory=True)
    data = _manifest()
    data["items"][0] |= {
        "fixture": fixture,
        "status": "accepted",
        "evidence": [evidence],
        "review": {"decision": "accepted", "reference": "https://github.com/HorneroOS/qa/pull/99"},
    }
    manifest = tmp_path / "acceptance.yaml"
    manifest.write_text(yaml.safe_dump(data), encoding="utf-8")

    report = evaluate(manifest, runs_dir)

    assert report["recommendation"] == "blocked"
    assert any(
        "fixture manifest path is unsafe" in reason for reason in report["items"][0]["blocking_reasons"]
    )


def test_invalid_screenshot_bytes_and_non_pr_review_link_block(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    evidence, _ = _accepted_run(runs_dir, tmp_path)
    data = _manifest()
    data["items"][0] |= {
        "fixture": _approved_fixture(tmp_path),
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


def test_jpeg_with_png_name_and_matching_sidecar_is_rejected(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    evidence, _ = _accepted_run(runs_dir, tmp_path)
    data = _manifest()
    data["items"][0] |= {
        "fixture": _approved_fixture(tmp_path),
        "status": "accepted",
        "evidence": [evidence],
        "review": {"decision": "accepted", "reference": "https://github.com/HorneroOS/qa/pull/99"},
    }
    output = io.BytesIO()
    Image.new("RGB", (1, 1)).save(output, format="JPEG")
    jpeg = output.getvalue()
    shot = runs_dir / "run-1/screenshots/frame.png"
    shot.write_bytes(jpeg)
    sidecar = json.loads(shot.with_suffix(".json").read_text(encoding="utf-8"))
    sidecar["sha256"] = hashlib.sha256(jpeg).hexdigest()
    shot.with_suffix(".json").write_text(json.dumps(sidecar), encoding="utf-8")
    manifest = tmp_path / "acceptance.yaml"
    manifest.write_text(yaml.safe_dump(data), encoding="utf-8")

    report = evaluate(manifest, runs_dir)

    assert report["recommendation"] == "blocked"
    assert any("not a valid PNG" in reason for reason in report["items"][0]["blocking_reasons"])


def test_failed_assertion_cannot_be_hidden_by_pass_result(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    evidence, _ = _accepted_run(runs_dir, tmp_path)
    data = _manifest()
    data["items"][0] |= {
        "fixture": _approved_fixture(tmp_path),
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
        "fixture": _approved_fixture(tmp_path),
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


def test_duplicate_proof_assertions_do_not_hide_an_unchecked_criterion(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    evidence, _ = _accepted_run(runs_dir, tmp_path)
    data = _manifest()
    data["items"][0] |= {
        "fixture": _approved_fixture(tmp_path),
        "status": "accepted",
        "evidence": [evidence],
        "review": {"decision": "accepted", "reference": "https://github.com/HorneroOS/qa/pull/99"},
    }
    (runs_dir / "run-1/assertions.json").write_text(
        '[{"kind":"probe","where":"proof 0","ok":true,"detail":"ready"},'
        '{"kind":"probe","where":"proof 0","ok":true,"detail":"ready again"}]\n',
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
        "fixture": {
            "id": "studio-doc-review",
            "approved": True,
            "sha256": None,
            "manifest": None,
            "notes": "Review fixture.",
        },
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
