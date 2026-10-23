"""Generate a deterministic scenario-by-execution ledger from reviewed evidence."""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import yaml

from hornero_qa.scenario import ScenarioError, discover, load

TRIAGE_PATH = Path("docs/scenario-triage.yaml")
EVIDENCE_ROOTS = (Path("docs/evidence"), Path(".github/evidence"))
SCREENSHOT_SCHEMA = "hornero.qa.screenshot/1"
APPEARANCE_SCHEMA = "hornero.appearance-evidence/1"
RUN_SCHEMA = "hornero.qa.run/1"


class MatrixError(ValueError):
    """Invalid or incomplete matrix inputs."""


@dataclass(frozen=True)
class Execution:
    timestamp: datetime
    result: str
    evidence: str
    quality: int


def _timestamp(value: Any, *, source: Path) -> datetime:
    if not isinstance(value, str):
        raise MatrixError(f"{source}: expected an ISO date or timestamp")
    try:
        if len(value) == 10:
            parsed = date.fromisoformat(value)
            return datetime.combine(parsed, datetime.min.time(), tzinfo=UTC)
        parsed_datetime = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed_datetime.tzinfo is None:
            raise ValueError("timestamp must include a timezone")
        return parsed_datetime.astimezone(UTC)
    except ValueError as exc:
        raise MatrixError(f"{source}: invalid ISO date/timestamp {value!r}") from exc


def _tracked_files(repo_root: Path) -> set[str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files", "-z"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise MatrixError(f"cannot list tracked evidence under {repo_root}: {exc}") from exc
    return {path for path in result.stdout.split("\0") if path}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MatrixError(f"{path}: cannot read JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise MatrixError(f"{path}: expected a JSON object")
    return data


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as evidence:
        for chunk in iter(lambda: evidence.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _link(repo_root: Path, path: Path, label: str) -> str:
    try:
        relative = path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise MatrixError(f"evidence must be inside the repository: {path}") from exc
    return f"[{label}]({relative})"


def resolve_repo_path(repo_root: Path, path: Path) -> Path:
    """Resolve relative CLI paths against the repository, independent of CWD."""
    return path if path.is_absolute() else repo_root / path


def _load_triage(repo_root: Path, scenario_ids: set[str]) -> dict[str, dict[str, str]]:
    path = repo_root / TRIAGE_PATH
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise MatrixError(f"{path}: cannot load triage: {exc}") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("scenarios"), dict):
        raise MatrixError(f"{path}: expected a top-level scenarios mapping")
    entries: dict[str, dict[str, str]] = {}
    for scenario_id, value in raw["scenarios"].items():
        if not isinstance(scenario_id, str) or not isinstance(value, dict):
            raise MatrixError(f"{path}: each scenario entry must be a mapping")
        decision = value.get("decision")
        rationale = value.get("rationale")
        schedule = value.get("schedule", "")
        if decision not in {"keep", "fix", "retire"}:
            raise MatrixError(f"{path}: {scenario_id}: decision must be keep, fix, or retire")
        if not isinstance(rationale, str) or not rationale.strip():
            raise MatrixError(f"{path}: {scenario_id}: rationale is required")
        if decision == "keep" and (not isinstance(schedule, str) or not schedule.strip()):
            raise MatrixError(f"{path}: {scenario_id}: keep decisions require a schedule")
        entries[scenario_id] = {
            "decision": decision,
            "rationale": rationale.strip(),
            "schedule": schedule.strip() if isinstance(schedule, str) else "",
        }
    missing = sorted(scenario_ids - entries.keys())
    stale = sorted(entries.keys() - scenario_ids)
    if missing or stale:
        details = []
        if missing:
            details.append(f"missing triage for: {', '.join(missing)}")
        if stale:
            details.append(f"triage references unknown scenarios: {', '.join(stale)}")
        raise MatrixError(f"{path}: {'; '.join(details)}")
    return entries


def _collect_sidecars(repo_root: Path, scenario_ids: set[str]) -> dict[str, list[Execution]]:
    executions: dict[str, list[Execution]] = {scenario_id: [] for scenario_id in scenario_ids}
    tracked_files = _tracked_files(repo_root)
    seen: set[Path] = set()
    for root in EVIDENCE_ROOTS:
        base = repo_root / root
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.json")):
            if path.relative_to(repo_root).as_posix() not in tracked_files:
                continue
            relative = path.relative_to(base)
            if path.name in {"run.json", "result.json", "assertions.json"} or any(
                (base / parent / "run.json").is_file() for parent in relative.parents
            ):
                continue
            if path in seen:
                continue
            seen.add(path)
            data = _read_json(path)
            schema = data.get("schema")
            if schema == SCREENSHOT_SCHEMA:
                filename = data.get("file")
                if not isinstance(filename, str):
                    raise MatrixError(f"{path}: screenshot sidecar has no file")
                records = [
                    (data.get("scenario"), data.get("captured"), path.parent / filename, data.get("sha256"))
                ]
            elif schema == APPEARANCE_SCHEMA:
                captured = data.get("captured")
                runs = data.get("runs", {})
                if not isinstance(runs, dict):
                    raise MatrixError(f"{path}: runs must be an object")
                records = [
                    (entry.get("scenario"), captured, path.parent / filename, entry.get("sha256"))
                    for filename, entry in runs.items()
                    if isinstance(filename, str) and isinstance(entry, dict)
                ]
            else:
                continue
            for scenario_id, captured, evidence_path, expected_hash in records:
                if not isinstance(scenario_id, str) or scenario_id not in scenario_ids:
                    continue
                if not evidence_path.is_file():
                    raise MatrixError(f"{path}: evidence file is missing: {evidence_path}")
                if evidence_path.relative_to(repo_root).as_posix() not in tracked_files:
                    raise MatrixError(f"{path}: evidence file is not tracked: {evidence_path}")
                if not isinstance(expected_hash, str) or _sha256(evidence_path) != expected_hash:
                    raise MatrixError(f"{path}: evidence hash does not match {evidence_path}")
                timestamp = _timestamp(captured, source=path)
                executions[str(scenario_id)].append(
                    Execution(
                        timestamp=timestamp,
                        result="Evidence only; result unavailable",
                        evidence=_link(repo_root, evidence_path, "screenshot evidence"),
                        quality=1,
                    )
                )
    return executions


def _collect_bundles(
    repo_root: Path, runs_dir: Path, scenario_ids: set[str], executions: dict[str, list[Execution]]
) -> None:
    if not runs_dir.exists():
        return
    tracked_files = _tracked_files(repo_root)
    for run_file in sorted(runs_dir.rglob("run.json")):
        if run_file.relative_to(repo_root).as_posix() not in tracked_files:
            continue
        run = _read_json(run_file)
        scenario_id = run.get("scenario")
        if not isinstance(scenario_id, str) or scenario_id not in scenario_ids:
            continue
        if run.get("schema") != RUN_SCHEMA:
            raise MatrixError(f"{run_file}: unsupported run schema {run.get('schema')!r}")
        run_id = run.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            raise MatrixError(f"{run_file}: run_id is required")
        started = _timestamp(run.get("started"), source=run_file)
        root = run_file.parent
        result_file = root / "result.json"
        result = (
            _read_json(result_file)
            if result_file.exists() and result_file.relative_to(repo_root).as_posix() in tracked_files
            else None
        )
        if result is not None:
            if result.get("run_id") != run_id:
                raise MatrixError(f"{result_file}: run_id does not match run metadata")
            finished = _timestamp(result.get("finished"), source=result_file)
            if finished < started:
                raise MatrixError(f"{result_file}: finished timestamp precedes run start")
        else:
            finished = started
        required_files = (root / "scenario.yaml", root / "actions.jsonl", root / "assertions.json")
        missing = [
            path.name
            for path in (*required_files, result_file)
            if not path.is_file() or path.relative_to(repo_root).as_posix() not in tracked_files
        ]
        if missing:
            evidence_path = result_file if result else run_file
            executions[str(scenario_id)].append(
                Execution(
                    finished,
                    f"Incomplete bundle; missing {', '.join(missing)}",
                    _link(repo_root, evidence_path, "run result" if result else "run metadata"),
                    2,
                )
            )
            continue
        try:
            bundle_scenario = load(root / "scenario.yaml")
        except ScenarioError as exc:
            raise MatrixError(f"{root / 'scenario.yaml'}: invalid bundled scenario: {exc}") from exc
        if bundle_scenario.id != scenario_id:
            raise MatrixError(f"{root / 'scenario.yaml'}: scenario ID does not match run metadata")
        verdict: Any = result.get("verdict") if result is not None else None
        if result is not None:
            if verdict not in {"pass", "fail", "inconclusive"}:
                raise MatrixError(f"{result_file}: unknown verdict {verdict!r}")
            missing_artifact: str | None = None
            for artifact in ("screenshots", "logs"):
                policy = bundle_scenario.artifacts.get(artifact, "always")
                required = verdict != "pass" or policy == "always"
                prefix = f"{(root / artifact).relative_to(repo_root).as_posix()}/"
                if required and not any(path.startswith(prefix) for path in tracked_files):
                    missing_artifact = artifact
                    break
            if missing_artifact:
                executions[str(scenario_id)].append(
                    Execution(
                        finished,
                        f"Incomplete bundle; missing {missing_artifact}/",
                        _link(repo_root, result_file, "run result"),
                        2,
                    )
                )
                continue
        try:
            assertions = json.loads((root / "assertions.json").read_text(encoding="utf-8"))
            actions = [
                json.loads(line)
                for line in (root / "actions.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except (OSError, json.JSONDecodeError) as exc:
            raise MatrixError(f"{root}: invalid assertion or action evidence: {exc}") from exc
        if not isinstance(assertions, list) or any(not isinstance(action, dict) for action in actions):
            raise MatrixError(f"{root}: assertions must be a list and actions must be JSON objects")
        if result is None:
            executions[str(scenario_id)].append(
                Execution(
                    started,
                    "Incomplete bundle; result unavailable",
                    _link(repo_root, run_file, "run metadata"),
                    2,
                )
            )
            continue
        label = {"pass": "PASS", "fail": "FAIL", "inconclusive": "INCONCLUSIVE"}[str(verdict)]
        failure_class = result.get("class")
        if failure_class:
            label += f" ({failure_class})"
        report = root / "report.html"
        evidence_path = report if report.exists() else result_file
        executions[str(scenario_id)].append(
            Execution(finished, label, _link(repo_root, evidence_path, "run report"), 3)
        )


def _escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def generate_matrix(repo_root: Path, runs_dir: Path) -> str:
    """Return the committed matrix, failing closed on missing triage or malformed evidence."""
    scenario_paths = discover(repo_root / "scenarios")
    scenarios = [load(path) for path in scenario_paths]
    scenario_ids = {scenario.id for scenario in scenarios}
    if len(scenario_ids) != len(scenarios):
        raise MatrixError("scenario IDs are not unique")
    triage = _load_triage(repo_root, scenario_ids)
    executions = _collect_sidecars(repo_root, scenario_ids)
    resolved_runs = runs_dir if runs_dir.is_absolute() else repo_root / runs_dir
    _collect_bundles(repo_root, resolved_runs, scenario_ids, executions)

    lines = [
        "# Scenario execution matrix",
        "",
        "Generated by `hornero-qa matrix`; CI checks this file with `--check`.",
        "Only tracked evidence is included. "
        "Screenshot sidecars without a complete run result are never treated as PASS.",
        "",
        "| Scenario | Last execution | Result | Evidence | Triage | Decision / next action |",
        "|---|---|---|---|---|---|",
    ]
    for scenario in scenarios:
        history = executions[scenario.id]
        if history:
            latest = max(history, key=lambda item: (item.timestamp, item.quality, item.evidence))
            last_execution = latest.timestamp.date().isoformat()
            result, evidence = latest.result, latest.evidence
        else:
            last_execution, result, evidence = "—", "Never executed", "—"
        decision = triage[scenario.id]
        action = decision["schedule"] if decision["decision"] == "keep" else decision["rationale"]
        lines.append(
            "| "
            + " | ".join(
                (
                    f"`{scenario.id}`",
                    last_execution,
                    _escape(result),
                    evidence,
                    decision["decision"],
                    _escape(action),
                )
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "`PASS`, `FAIL`, and `INCONCLUSIVE` come only from a complete run bundle. "
            "`Evidence only` means a recognized screenshot sidecar exists but no result bundle is available. "
            "`Never executed` means no matching tracked run bundle or recognized sidecar was found.",
            "",
            "Triage rationale and scheduling decisions are recorded in "
            "[scenario-triage.yaml](scenario-triage.yaml).",
            "",
        ]
    )
    return "\n".join(lines)
