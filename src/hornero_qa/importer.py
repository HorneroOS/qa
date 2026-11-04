"""Import one manual evidence directory into a tracked run bundle.

Manual install runs (docs/INSTALL-PAIRWISE.md) leave a free-form directory:
a ``RESULT.md`` plus ``*.png`` screenshots. This module converts exactly one
such directory into the standard bundle layout (see evidence.py) under a
runs directory, without inventing evidence:

- the scenario id and the verdict are explicit caller inputs; the verdict is
  never parsed or inferred from the RESULT.md prose;
- ISO/product provenance is recorded exactly as supplied by the caller;
- RESULT.md is copied unchanged to ``logs/RESULT.md``;
- assertions contain a single manual record pointing at RESULT.md, never
  fabricated per-probe results.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from hornero_qa import __version__
from hornero_qa.evidence import BUNDLE_SCHEMA, SIDECAR_SCHEMA
from hornero_qa.scenario import Scenario
from hornero_qa.taxonomy import FailureClass, Verdict, is_regression
from hornero_qa.vision import frame_sha256

_SHA256 = re.compile(r"[0-9a-f]{64}")
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class EvidenceImportError(ValueError):
    """The source directory or caller inputs cannot form an honest bundle."""


@dataclass(frozen=True)
class ImportRequest:
    source: Path
    scenario: Scenario
    verdict: str
    reason: str
    product: dict[str, str]
    runs_dir: Path
    attempt: int = 1
    engine: str = "manual"
    started: datetime | None = None
    finished: datetime | None = None
    failure_class: str | None = None
    environment: dict[str, str] = field(default_factory=dict)


def _dump(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def _iso(when: datetime) -> str:
    return when.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _mtime(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)


def _png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as image:
        header = image.read(24)
    if len(header) != 24 or header[:8] != _PNG_MAGIC or header[12:16] != b"IHDR":
        raise EvidenceImportError(f"screenshot is not a valid PNG: {path}")
    width, height = int.from_bytes(header[16:20], "big"), int.from_bytes(header[20:24], "big")
    if width == 0 or height == 0:
        raise EvidenceImportError(f"screenshot has zero dimensions: {path}")
    return width, height


def _natural_key(name: str) -> list[int | str]:
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", name)]


def _stem(name: str) -> str:
    stem = re.sub(r"^\d+[-_ ]+", "", Path(name).stem.lower())
    stem = re.sub(r"[^a-z0-9-_]+", "-", stem).strip("-")
    return stem or "frame"


def import_evidence(request: ImportRequest) -> Path:
    """Write one bundle for `request` and return its root. Never overwrites."""
    if request.verdict not in {v.value for v in Verdict}:
        raise EvidenceImportError(f"verdict must be pass, fail or inconclusive, got {request.verdict!r}")
    if not request.reason.strip():
        raise EvidenceImportError("a reason for the verdict is required")
    if request.failure_class is not None and request.failure_class not in {f.value for f in FailureClass}:
        raise EvidenceImportError(f"unknown failure class: {request.failure_class!r}")
    if request.failure_class is not None and request.verdict == Verdict.PASS.value:
        raise EvidenceImportError("a pass verdict cannot carry a failure class")
    if request.attempt < 1:
        raise EvidenceImportError("attempt must be >= 1")
    iso_sha256 = request.product.get("iso_sha256", "")
    if not _SHA256.fullmatch(iso_sha256):
        raise EvidenceImportError("product iso_sha256 must be a full lowercase SHA-256")
    source = request.source
    if not source.is_dir():
        raise EvidenceImportError(f"source evidence directory does not exist: {source}")
    result_md = source / "RESULT.md"
    if not result_md.is_file():
        raise EvidenceImportError(f"{source}: RESULT.md is required")
    shots = sorted(source.glob("*.png"), key=lambda shot: _natural_key(shot.name))
    if not shots:
        raise EvidenceImportError(f"{source}: at least one .png screenshot is required")
    sizes = [_png_size(shot) for shot in shots]

    started = request.started or min(_mtime(shot) for shot in shots)
    finished = request.finished or max(_mtime(shot) for shot in shots)
    if started.tzinfo is None or finished.tzinfo is None:
        raise EvidenceImportError("started/finished must include a timezone")
    started, finished = started.astimezone(UTC), finished.astimezone(UTC)
    if finished < started:
        raise EvidenceImportError("finished must not precede started")
    wall_s = int((finished - started).total_seconds())

    scenario = request.scenario
    slug = scenario.id.replace("/", "-")
    run_id = f"{started:%Y%m%dT%H%M%SZ}-{slug}-{request.attempt}"
    root = request.runs_dir / run_id
    if root.exists():
        raise EvidenceImportError(f"bundle already exists, refusing to overwrite: {root}")

    environment: dict[str, Any] = {
        "engine": request.engine,
        "hornero_qa": __version__,
        "source_dir": source.name,
        "imported_via": "hornero-qa import",
    } | dict(request.environment)
    run: dict[str, Any] = {
        "schema": BUNDLE_SCHEMA,
        "run_id": run_id,
        "started": _iso(started),
        "scenario": scenario.id,
        "covers": list(scenario.covers),
        "instruction": scenario.instruction,
        "attempt": request.attempt,
        "product": dict(request.product),
        "environment": environment,
    }

    (root / "screenshots").mkdir(parents=True, exist_ok=False)
    try:
        (root / "logs").mkdir()
        scenario_text = scenario.text or (
            scenario.source.read_text(encoding="utf-8") if scenario.source else ""
        )
        if not scenario_text:
            raise EvidenceImportError(f"scenario {scenario.id!r} has no source text to bundle")
        (root / "scenario.yaml").write_text(scenario_text, encoding="utf-8")
        _dump(root / "run.json", run)
        shutil.copyfile(result_md, root / "logs" / "RESULT.md")

        source_map: list[tuple[str, str]] = []
        for seq, (shot, (width, height)) in enumerate(zip(shots, sizes, strict=True), start=1):
            dst = root / "screenshots" / f"{seq:03d}-{_stem(shot.name)}.png"
            source_map.append((dst.name, shot.name))
            shutil.copyfile(shot, dst)
            captured = _mtime(shot)
            shot_env = dict(environment)
            shot_env["captured_resolution"] = f"{width}x{height}"
            _dump(
                dst.with_suffix(".json"),
                {
                    "schema": SIDECAR_SCHEMA,
                    "file": dst.name,
                    "sha256": frame_sha256(dst),
                    "run_id": run_id,
                    "scenario": scenario.id,
                    "captured": _iso(captured),
                    "t": max(0, int((captured - started).total_seconds())),
                    "product": dict(request.product),
                    "environment": shot_env,
                    "source_file": shot.name,
                },
            )

        # RESULT.md cites screenshots by their source names and may link
        # sibling manual evidence dirs (../<dir>/RESULT.md); it is copied
        # byte-identical, so record the bundled<->source mapping here.
        (root / "logs" / "source-map.md").write_text(
            "# Source map (generated by hornero-qa import)\n\n"
            "RESULT.md is copied byte-identical from the manual evidence\n"
            "directory; its screenshot citations use source file names and\n"
            "its ../<dir>/ references point at sibling manual evidence\n"
            "directories of the same session, imported as separate bundles.\n\n"
            "| Bundled screenshot | Source file |\n|---|---|\n"
            + "".join(f"| screenshots/{bundled} | {original} |\n" for bundled, original in source_map),
            encoding="utf-8",
        )

        actions = [
            {"t": 0, "kind": "manual-run", "source": source.name},
            {
                "t": wall_s,
                "kind": "import",
                "tool": "hornero-qa import",
                "result_md": "logs/RESULT.md",
                "screenshots": len(shots),
            },
        ]
        (root / "actions.jsonl").write_text(
            "".join(json.dumps(action) + "\n" for action in actions), encoding="utf-8"
        )
        _dump(
            root / "assertions.json",
            [
                {
                    "t": wall_s,
                    "kind": "manual",
                    "ok": request.verdict == Verdict.PASS.value,
                    "where": "manual-import",
                    "note": "Operator-supplied verdict for the manual run; see RESULT.md. "
                    "No scenario proof probe results are recorded by the importer.",
                    "detail": "logs/RESULT.md",
                }
            ],
        )
        # Never derive blame from the verdict alone: only an explicit
        # operator-supplied class is recorded for fail; inconclusive keeps
        # its taxonomy class.
        failure_class = (
            None
            if request.verdict == Verdict.PASS.value
            else request.failure_class
            if request.verdict == Verdict.FAIL.value
            else request.failure_class or FailureClass.INCONCLUSIVE.value
        )
        regression = is_regression(FailureClass(failure_class) if failure_class else None)
        _dump(
            root / "result.json",
            {
                "run_id": run_id,
                "finished": _iso(finished),
                "wall_s": wall_s,
                "verdict": request.verdict,
                "class": failure_class,
                "regression": regression,
                "reason": request.reason,
                "actions": len(actions),
                "driver_end": None,
                "review": None,
            },
        )
        from hornero_qa.report import write_report

        write_report(root)
    except BaseException:
        shutil.rmtree(root, ignore_errors=True)
        raise
    return root
