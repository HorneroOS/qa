"""Fail-closed Studio acceptance evidence index; never changes product maturity."""

from __future__ import annotations

import hashlib
import io
import json
import re
from pathlib import Path
from typing import Any

import jsonschema
import yaml
from PIL import Image

from hornero_qa.scenario import ScenarioError
from hornero_qa.scenario import parse as parse_scenario

SCHEMA_PATH = Path(__file__).parent / "schemas" / "studio_acceptance.schema.json"
RUN_SCHEMA = "hornero.qa.run/1"
REQUIRED_BUNDLE_FILES = ("run.json", "result.json", "scenario.yaml", "actions.jsonl", "assertions.json")
REVIEW_URL = re.compile(r"^https://github\.com/HorneroOS/[A-Za-z0-9_.-]+/pull/[1-9][0-9]*$")
PIN_FIELDS = (
    "shell_sha",
    "config_sha",
    "horneroctl_sha256",
    "guest_sha",
    "iso_sha256",
    "manifest_sha256",
    "catalogue_sha256",
    "hardware_fixture",
    "hardware_fixture_sha256",
)


class StudioGateError(ValueError):
    """Invalid Studio evidence index or unsafe bundle reference."""


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StudioGateError(f"{path}: cannot read JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise StudioGateError(f"{path}: expected a JSON object")
    return value


def _scenario_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as scenario:
        for chunk in iter(lambda: scenario.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_evidence(entry: dict[str, Any], runs_dir: Path) -> list[str]:
    if entry["kind"] == "review":
        if not REVIEW_URL.fullmatch(entry["reference"]):
            return ["review evidence must link to a HorneroOS pull request"]
        return []
    run_id = entry["run_id"]
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", run_id):
        return [f"invalid bundle ID {run_id!r}"]
    root = (runs_dir / run_id).resolve()
    base = runs_dir.resolve()
    if not root.is_relative_to(base) or (runs_dir / run_id).is_symlink():
        return [f"bundle {run_id!r} escapes the evidence directory"]
    missing = [
        name for name in REQUIRED_BUNDLE_FILES if not (root / name).is_file() or (root / name).is_symlink()
    ]
    if missing:
        return [f"bundle {run_id!r} is incomplete (missing {', '.join(missing)})"]
    run = _read_object(root / "run.json")
    result = _read_object(root / "result.json")
    if run.get("schema") != RUN_SCHEMA or run.get("run_id") != run_id:
        return [f"bundle {run_id!r} has unsupported or mismatched run metadata"]
    if run.get("scenario") != entry["scenario"]:
        return [f"bundle {run_id!r} scenario does not match {entry['scenario']!r}"]
    if result.get("run_id") != run_id or result.get("verdict") != "pass":
        return [f"bundle {run_id!r} is not a matching PASS result"]
    if result.get("class") not in (None, "pass"):
        return [f"bundle {run_id!r} has an invalid PASS result class"]
    try:
        scenario_text = (root / "scenario.yaml").read_text(encoding="utf-8")
        scenario = parse_scenario(scenario_text)
        actions = [
            json.loads(line)
            for line in (root / "actions.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assertions = json.loads((root / "assertions.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, yaml.YAMLError, ScenarioError) as exc:
        return [f"bundle {run_id!r} contains invalid evidence data: {exc}"]
    if scenario.id != entry["scenario"]:
        return [f"bundle {run_id!r} scenario document has a mismatched ID"]
    proofs = scenario.proof
    if not isinstance(proofs, list) or not proofs:
        return [f"bundle {run_id!r} scenario has no deterministic proof criteria"]
    proof_kinds: dict[str, str] = {}
    for index, proof in enumerate(proofs):
        if not isinstance(proof, dict):
            return [f"bundle {run_id!r} scenario proof {index} is malformed"]
        kinds = [key for key in proof if key != "note"]
        if len(kinds) != 1 or not isinstance(kinds[0], str):
            return [f"bundle {run_id!r} scenario proof {index} must declare exactly one check"]
        proof_kinds[f"proof {index}"] = kinds[0]
    if not actions or not all(
        isinstance(action, dict)
        and isinstance(action.get("kind"), str)
        and isinstance(action.get("t"), (int, float))
        for action in actions
    ):
        return [f"bundle {run_id!r} has no valid action records"]
    if (
        not isinstance(assertions, list)
        or not assertions
        or not all(
            isinstance(assertion, dict)
            and isinstance(assertion.get("kind"), str)
            and isinstance(assertion.get("where"), str)
            and isinstance(assertion.get("ok"), bool)
            and isinstance(assertion.get("detail"), str)
            for assertion in assertions
        )
    ):
        return [f"bundle {run_id!r} has no valid assertion records"]
    if not all(assertion["ok"] for assertion in assertions):
        return [f"bundle {run_id!r} contains a failed assertion despite its PASS result"]
    recorded_proofs = [assertion for assertion in assertions if assertion["where"].startswith("proof ")]
    recorded_indices = [assertion["where"] for assertion in recorded_proofs]
    if (
        len(set(recorded_indices)) != len(recorded_indices)
        or set(recorded_indices) != set(proof_kinds)
        or any(
            assertion["where"] not in proof_kinds or assertion["kind"] != proof_kinds[assertion["where"]]
            for assertion in recorded_proofs
        )
    ):
        return [f"bundle {run_id!r} assertions do not cover the scenario's declared proof criteria"]
    scenario_path = root / "scenario.yaml"
    if _scenario_digest(scenario_path) != entry["scenario_sha256"]:
        return [f"bundle {run_id!r} uses a stale scenario revision"]
    pins = entry["pins"]
    product = run.get("product", {})
    environment = run.get("environment", {})
    catalogues = run.get("catalogues", {})
    if not all(isinstance(value, dict) for value in (product, environment, catalogues)):
        return [f"bundle {run_id!r} has malformed product or environment metadata"]
    actual = {
        "shell_sha": product.get("shell_sha"),
        "config_sha": product.get("config_sha"),
        "horneroctl_sha256": product.get("horneroctl_sha256"),
        "guest_sha": product.get("guest_sha"),
        "iso_sha256": product.get("iso_sha256"),
        "manifest_sha256": product.get("manifest_sha256"),
        "catalogue_sha256": product.get("catalogue_sha256"),
        "hardware_fixture": product.get("hardware_fixture"),
        "hardware_fixture_sha256": product.get("hardware_fixture_sha256"),
    }
    stale = [name for name in PIN_FIELDS if actual[name] != pins[name]]
    if stale:
        return [f"bundle {run_id!r} is missing or differs from pinned provenance: {', '.join(stale)}"]
    if actual["hardware_fixture"] != entry.get("approved_fixture_id"):
        return [f"bundle {run_id!r} does not use the owner-approved hardware fixture"]
    if actual["hardware_fixture_sha256"] != entry.get("approved_fixture_sha256"):
        return [f"bundle {run_id!r} fixture digest does not match the owner-approved fixture"]
    screenshots = list((root / "screenshots").glob("*.png"))
    if (root / "screenshots").is_symlink() or not screenshots:
        return [f"bundle {run_id!r} has no screenshot artifact"]
    for shot in screenshots:
        sidecar = shot.with_suffix(".json")
        if shot.is_symlink() or not sidecar.is_file() or sidecar.is_symlink():
            return [f"bundle {run_id!r} screenshot {shot.name!r} lacks a safe provenance sidecar"]
        try:
            payload = shot.read_bytes()
            metadata = _read_object(sidecar)
        except (OSError, StudioGateError) as exc:
            return [f"bundle {run_id!r} screenshot cannot be read: {exc}"]
        try:
            with Image.open(io.BytesIO(payload)) as image:
                image.verify()
        except (OSError, ValueError):
            return [f"bundle {run_id!r} screenshot {shot.name!r} is not a valid PNG"]
        if (
            metadata.get("schema") != "hornero.qa.screenshot/1"
            or metadata.get("file") != shot.name
            or metadata.get("run_id") != run_id
            or metadata.get("scenario") != entry["scenario"]
            or metadata.get("sha256") != hashlib.sha256(payload).hexdigest()
            or metadata.get("product") != product
        ):
            return [f"bundle {run_id!r} screenshot {shot.name!r} sidecar provenance is invalid"]
    if (root / "logs").is_symlink():
        return [f"bundle {run_id!r} log directory is unsafe"]
    log_files = [
        path
        for path in (root / "logs").glob("*")
        if path.is_file() and not path.is_symlink() and path.stat().st_size
    ]
    if not log_files:
        return [f"bundle {run_id!r} has no log artifact"]
    return []


def evaluate(manifest_path: Path, runs_dir: Path) -> dict[str, Any]:
    """Validate Studio gate inputs and report whether owners can review promotion evidence."""
    try:
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, yaml.YAMLError) as exc:
        raise StudioGateError(f"cannot load Studio acceptance index: {exc}") from exc
    errors = sorted(
        jsonschema.Draft202012Validator(schema).iter_errors(manifest),
        key=lambda err: list(err.path),
    )
    if errors:
        error = errors[0]
        location = ".".join(str(part) for part in error.path) or "root"
        raise StudioGateError(f"{manifest_path}: {location}: {error.message}")
    item_ids = [item["id"] for item in manifest["items"]]
    if len(item_ids) != len(set(item_ids)):
        raise StudioGateError(f"{manifest_path}: item IDs must be unique")

    results: list[dict[str, Any]] = []
    for item in manifest["items"]:
        conditional_unknown = item["condition"] == "when-enabled" and item["enabled"] is None
        required = item["required"] or (item["condition"] == "when-enabled" and item["enabled"] is True)
        reasons: list[str] = []
        if conditional_unknown:
            reasons.append("conditional applicability is unresolved")
        if required and item["status"] != "accepted":
            reasons.append(f"status is {item['status']}, not accepted")
        if required and not item["fixture"]["approved"]:
            reasons.append("fixture is not owner-approved")
        if required and not item["fixture"]["id"]:
            reasons.append("fixture has no stable ID")
        if (
            required
            and item["evidence_kind"] == "bundle"
            and item["fixture"]["approved"]
            and not item["fixture"].get("sha256")
        ):
            reasons.append("approved fixture has no pinned manifest SHA256")
        if required and item["review"]["decision"] != "accepted":
            reasons.append("human review is not accepted")
        if required and not item["review"]["reference"]:
            reasons.append("human review has no reference")
        if (
            required
            and item["review"]["decision"] == "accepted"
            and not REVIEW_URL.fullmatch(item["review"].get("reference") or "")
        ):
            reasons.append("human review must reference a HorneroOS pull request")
        for evidence in item["evidence"]:
            if evidence["kind"] == "review" and item["review"].get("reference") != evidence.get("reference"):
                reasons.append("review decision reference does not match the indexed pull request")
            if evidence["kind"] == "bundle":
                evidence["approved_fixture_id"] = item["fixture"]["id"]
                evidence["approved_fixture_sha256"] = item["fixture"].get("sha256")
            reasons.extend(_verify_evidence(evidence, runs_dir))
        if required and not item["evidence"]:
            reasons.append("no evidence is indexed")
        if required and not any(entry["kind"] == item["evidence_kind"] for entry in item["evidence"]):
            reasons.append(f"no {item['evidence_kind']} evidence is indexed")
        results.append({"id": item["id"], "status": item["status"], "blocking_reasons": reasons})

    required_ids = {
        entry["id"]
        for entry in manifest["items"]
        if entry["required"] or (entry["condition"] == "when-enabled" and entry["enabled"] is not False)
    }
    blockers = sum(bool(item["blocking_reasons"]) for item in results if item["id"] in required_ids)
    eligible = blockers == 0
    return {
        "schema": manifest["schema"],
        "eligible_for_owner_review": eligible,
        "recommendation": "ready_for_owner_review" if eligible else "blocked",
        "summary": (
            "Studio evidence is complete for product/installer owner review. "
            "QA does not set edition maturity."
            if eligible
            else f"Studio Preview recommendation blocked: {blockers} required evidence "
            "gate(s) are incomplete."
        ),
        "items": results,
    }
