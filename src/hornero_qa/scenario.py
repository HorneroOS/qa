"""Scenarios are reviewed product data: YAML validated against a JSON Schema."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

import jsonschema
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_DIR = REPO_ROOT / "scenarios"


def _schema() -> dict[str, Any]:
    text = resources.files("hornero_qa.schemas").joinpath("scenario.schema.json").read_text(encoding="utf-8")
    data: dict[str, Any] = json.loads(text)
    return data


class ScenarioError(ValueError):
    pass


@dataclass
class Scenario:
    id: str
    purpose: str
    instruction: str
    proof: list[dict[str, Any]]
    steps: list[dict[str, Any]] = field(default_factory=list)
    covers: list[str] = field(default_factory=list)
    requires: dict[str, Any] = field(default_factory=dict)
    setup: dict[str, Any] = field(default_factory=dict)
    budget: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    media: list[str] = field(default_factory=list)
    source: Path | None = None
    text: str = ""

    @property
    def wall_s(self) -> float:
        return float(self.budget.get("wall_s", 180))

    @property
    def max_actions(self) -> int:
        return int(self.budget.get("max_actions", 60))

    @property
    def max_malformed(self) -> int:
        return int(self.budget.get("max_malformed", 3))

    @property
    def resolution(self) -> tuple[int, int]:
        w, h = str(self.requires.get("resolution", "1280x800")).split("x")
        return int(w), int(h)

    @property
    def outputs(self) -> int:
        return int(self.requires.get("outputs", 1))


def parse(text: str, source: Path | None = None) -> Scenario:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ScenarioError(f"{source}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ScenarioError(f"{source}: scenario must be a mapping")
    try:
        jsonschema.validate(data, _schema())
    except jsonschema.ValidationError as exc:
        where = "/".join(str(p) for p in exc.absolute_path) or "<root>"
        raise ScenarioError(f"{source}: {where}: {exc.message}") from exc
    if source is not None:
        rel = (
            source.relative_to(SCENARIO_DIR).with_suffix("") if source.is_relative_to(SCENARIO_DIR) else None
        )
        if rel is not None and rel.as_posix() != data["id"]:
            raise ScenarioError(f"{source}: id {data['id']!r} must match its path {rel.as_posix()!r}")
    return Scenario(**data, source=source, text=text)


def load(path: str | Path) -> Scenario:
    p = Path(path)
    return parse(p.read_text(encoding="utf-8"), p.resolve())


def discover(root: Path = SCENARIO_DIR) -> list[Path]:
    return sorted(root.rglob("*.yaml"))


def resolve(name: str, root: Path = SCENARIO_DIR) -> Path:
    """Scenario id ('layouts/apply-cockpit-clear') or a path -> file path."""
    p = Path(name)
    if p.suffix == ".yaml" and p.exists():
        return p
    cand = root / f"{name}.yaml"
    if cand.exists():
        return cand
    raise ScenarioError(f"no scenario {name!r} (looked for {cand})")
