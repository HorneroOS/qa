from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest
import yaml

from hornero_qa.matrix import MatrixError, generate_matrix

SOURCE_SCENARIO = Path(__file__).parents[1] / "scenarios/smoke/desktop-ready.yaml"


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "scenarios/smoke").mkdir(parents=True)
    source = yaml.safe_load(SOURCE_SCENARIO.read_text(encoding="utf-8"))
    source["id"] = "smoke/with-evidence"
    source["artifacts"] = {"screenshots": "always", "logs": "on-failure"}
    (repo / "scenarios/smoke/with-evidence.yaml").write_text(yaml.safe_dump(source), encoding="utf-8")
    source["id"] = "smoke/never-run"
    (repo / "scenarios/smoke/never-run.yaml").write_text(yaml.safe_dump(source), encoding="utf-8")
    entries = {
        scenario_id: {
            "decision": "keep",
            "rationale": "Protects a distinct product behavior.",
            "schedule": "Next approved KVM window.",
        }
        for scenario_id in ("smoke/with-evidence", "smoke/never-run")
    }
    (repo / "docs").mkdir()
    (repo / "docs/scenario-triage.yaml").write_text(
        yaml.safe_dump({"scenarios": entries}, sort_keys=True), encoding="utf-8"
    )
    subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)
    return repo


def test_sidecar_is_unverified_and_missing_evidence_is_never_executed(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    evidence = repo / "docs/evidence/old-run"
    evidence.mkdir(parents=True)
    for filename, captured in (
        ("frame-earlier.png", "2026-10-02T08:00:00Z"),
        ("frame-latest.png", "2026-10-02T08:30:00Z"),
    ):
        image = evidence / filename
        image.write_bytes(b"PNG fixture")
        sidecar = {
            "schema": "hornero.qa.screenshot/1",
            "scenario": "smoke/with-evidence",
            "captured": captured,
            "run_id": "old-run",
            "file": filename,
            "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
        }
        (evidence / f"{filename[:-4]}.json").write_text(json.dumps(sidecar), encoding="utf-8")
        subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "add",
                str(image.relative_to(repo)),
                str((evidence / f"{filename[:-4]}.json").relative_to(repo)),
            ],
            check=True,
            capture_output=True,
        )

    matrix = generate_matrix(repo, repo / "docs/evidence/runs")

    assert "2026-10-02 | Evidence only; result unavailable" in matrix
    assert "[screenshot evidence](evidence/old-run/frame-latest.png)" in matrix
    assert "Never executed" in matrix
    assert " | PASS | " not in matrix


def test_github_evidence_link_is_relative_to_the_matrix_document(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    evidence = repo / ".github/evidence/manual"
    evidence.mkdir(parents=True)
    image = evidence / "frame.png"
    image.write_bytes(b"PNG fixture")
    (evidence / "frame.json").write_text(
        json.dumps(
            {
                "schema": "hornero.qa.screenshot/1",
                "scenario": "smoke/with-evidence",
                "captured": "2026-10-02T08:30:00Z",
                "run_id": "manual-run",
                "file": image.name,
                "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "-C", str(repo), "add", ".github/evidence/manual"], check=True, capture_output=True
    )

    matrix = generate_matrix(repo, repo / "docs/evidence/runs")

    assert "[screenshot evidence](../.github/evidence/manual/frame.png)" in matrix


def test_untracked_sidecars_do_not_change_the_committed_matrix(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    evidence = repo / "docs/evidence/local-run"
    evidence.mkdir(parents=True)
    image = evidence / "local.png"
    image.write_bytes(b"PNG fixture")
    (evidence / "local.json").write_text(
        json.dumps(
            {
                "schema": "hornero.qa.screenshot/1",
                "scenario": "smoke/with-evidence",
                "captured": "2026-10-02T08:00:00Z",
                "run_id": "local-run",
                "file": image.name,
                "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
            }
        ),
        encoding="utf-8",
    )

    matrix = generate_matrix(repo, repo / "docs/evidence/runs")

    assert "`smoke/with-evidence` | — | Never executed" in matrix


def test_complete_run_bundle_supplies_the_result_and_date(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    run_dir = repo / "docs/evidence/runs/run-1"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "schema": "hornero.qa.run/1",
                "scenario": "smoke/with-evidence",
                "run_id": "run-1",
                "started": "2026-10-03T07:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "result.json").write_text(
        json.dumps({"run_id": "run-1", "finished": "2026-10-03T07:01:00Z", "verdict": "pass"}),
        encoding="utf-8",
    )
    (run_dir / "scenario.yaml").write_text(
        (repo / "scenarios/smoke/with-evidence.yaml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (run_dir / "actions.jsonl").write_text("", encoding="utf-8")
    (run_dir / "assertions.json").write_text("[]", encoding="utf-8")
    (run_dir / "screenshots").mkdir()
    (run_dir / "screenshots/capture.png").write_bytes(b"PNG fixture")
    subprocess.run(
        ["git", "-C", str(repo), "add", str(run_dir.relative_to(repo))], check=True, capture_output=True
    )
    # Local, untracked report output must not leak into the committed matrix.
    (run_dir / "report.html").write_text("local report", encoding="utf-8")

    matrix = generate_matrix(repo, repo / "docs/evidence/runs")

    assert "2026-10-03 | PASS" in matrix
    assert "[run report](evidence/runs/run-1/result.json)" in matrix
    assert "2026-10-02 | Evidence only" not in matrix


def test_bundle_without_result_is_not_reported_as_pass(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    run_dir = repo / "docs/evidence/runs/run-incomplete"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "schema": "hornero.qa.run/1",
                "scenario": "smoke/with-evidence",
                "run_id": "run-incomplete",
                "started": "2026-10-03T07:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "-C", str(repo), "add", str((run_dir / "run.json").relative_to(repo))],
        check=True,
        capture_output=True,
    )

    matrix = generate_matrix(repo, repo / "docs/evidence/runs")

    assert "Incomplete bundle; missing" in matrix
    assert " | PASS | " not in matrix


def test_result_without_required_bundle_artifacts_is_not_reported_as_pass(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    run_dir = repo / "docs/evidence/runs/run-truncated"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "schema": "hornero.qa.run/1",
                "scenario": "smoke/with-evidence",
                "run_id": "run-truncated",
                "started": "2026-10-03T07:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "result.json").write_text(
        json.dumps({"run_id": "run-truncated", "finished": "2026-10-03T07:01:00Z", "verdict": "pass"}),
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "-C", str(repo), "add", str(run_dir.relative_to(repo))], check=True, capture_output=True
    )

    matrix = generate_matrix(repo, repo / "docs/evidence/runs")

    assert "Incomplete bundle; missing scenario.yaml" in matrix
    assert " | PASS | " not in matrix


def test_result_timestamp_cannot_precede_run_start(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    run_dir = repo / "docs/evidence/runs/run-backwards"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "schema": "hornero.qa.run/1",
                "scenario": "smoke/with-evidence",
                "run_id": "run-backwards",
                "started": "2026-10-03T07:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "result.json").write_text(
        json.dumps({"run_id": "run-backwards", "finished": "2026-10-03T06:59:00Z", "verdict": "pass"}),
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "-C", str(repo), "add", str(run_dir.relative_to(repo))], check=True, capture_output=True
    )

    with pytest.raises(MatrixError, match="finished timestamp precedes run start"):
        generate_matrix(repo, repo / "docs/evidence/runs")


def test_bundle_result_must_match_its_run_id(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    run_dir = repo / "docs/evidence/runs/run-1"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "schema": "hornero.qa.run/1",
                "scenario": "smoke/with-evidence",
                "run_id": "run-1",
                "started": "2026-10-03T07:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "result.json").write_text(
        json.dumps({"run_id": "different-run", "finished": "2026-10-03T07:01:00Z", "verdict": "pass"}),
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "-C", str(repo), "add", str(run_dir.relative_to(repo))], check=True, capture_output=True
    )
    (run_dir / "scenario.yaml").write_text(
        (repo / "scenarios/smoke/with-evidence.yaml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (run_dir / "actions.jsonl").write_text("", encoding="utf-8")
    (run_dir / "assertions.json").write_text("[]", encoding="utf-8")
    (run_dir / "screenshots").mkdir()
    (run_dir / "logs").mkdir()
    (run_dir / "screenshots/capture.png").write_bytes(b"PNG fixture")
    (run_dir / "logs/guest.log").write_text("", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(repo), "add", str(run_dir.relative_to(repo))], check=True, capture_output=True
    )

    with pytest.raises(MatrixError, match="run_id does not match"):
        generate_matrix(repo, repo / "docs/evidence/runs")


def test_matrix_rejects_missing_triage(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    triage_path = repo / "docs/scenario-triage.yaml"
    triage = yaml.safe_load(triage_path.read_text(encoding="utf-8"))
    del triage["scenarios"]["smoke/never-run"]
    triage_path.write_text(yaml.safe_dump(triage), encoding="utf-8")

    with pytest.raises(MatrixError, match="missing triage for: smoke/never-run"):
        generate_matrix(repo, repo / "docs/evidence/runs")
