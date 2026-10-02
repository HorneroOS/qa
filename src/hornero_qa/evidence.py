"""Evidence bundles: one directory per run, readable by humans and machines.

Layout (docs/EVIDENCE.md):
    run.json, scenario.yaml, actions.jsonl, assertions.json, result.json,
    screenshots/NNN-<name>.png (+ .json sidecar), logs/, report.html
"""

from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hornero_qa.vision import frame_sha256

BUNDLE_SCHEMA = "hornero.qa.run/1"
SIDECAR_SCHEMA = "hornero.qa.screenshot/1"


def _dump(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8")


@dataclass
class Bundle:
    root: Path
    run: dict[str, Any]
    t0: float = field(default_factory=time.monotonic)
    _seq: int = 0
    _assertions: list[dict[str, Any]] = field(default_factory=list)
    _actions: Any = None

    @classmethod
    def create(cls, runs_dir: Path, run_id: str, run_meta: dict[str, Any], scenario_text: str) -> Bundle:
        root = runs_dir / run_id
        (root / "screenshots").mkdir(parents=True, exist_ok=False)
        (root / "logs").mkdir()
        (root / "scenario.yaml").write_text(scenario_text, encoding="utf-8")
        meta = {"schema": BUNDLE_SCHEMA, "run_id": run_id, "started": _now()} | run_meta
        _dump(root / "run.json", meta)
        bundle = cls(root=root, run=meta)
        bundle._actions = (root / "actions.jsonl").open("w", encoding="utf-8")
        return bundle

    def elapsed(self) -> float:
        return round(time.monotonic() - self.t0, 3)

    def action(self, kind: str, **data: Any) -> None:
        """Append one record to the intent/action log."""
        rec = {"t": self.elapsed(), "kind": kind} | data
        self._actions.write(json.dumps(rec) + "\n")
        self._actions.flush()

    def assertion(self, record: dict[str, Any]) -> None:
        self._assertions.append({"t": self.elapsed()} | record)

    def screenshot(self, src: Path, name: str, extra: dict[str, Any] | None = None) -> Path:
        """Keep a frame with a provenance sidecar (website media pipeline input)."""
        self._seq += 1
        dst = self.root / "screenshots" / f"{self._seq:03d}-{name}.png"
        shutil.copyfile(src, dst)
        sidecar = {
            "schema": SIDECAR_SCHEMA,
            "file": dst.name,
            "sha256": frame_sha256(dst),
            "run_id": self.run["run_id"],
            "scenario": self.run.get("scenario"),
            "captured": _now(),
            "t": self.elapsed(),
            "product": self.run.get("product", {}),
            "environment": self.run.get("environment", {}),
        } | (extra or {})
        _dump(dst.with_suffix(".json"), sidecar)
        return dst

    @property
    def assertions(self) -> list[dict[str, Any]]:
        return list(self._assertions)

    def finish(self, result: dict[str, Any]) -> dict[str, Any]:
        if self._actions:
            self._actions.close()
        _dump(self.root / "assertions.json", self._assertions)
        final = {"run_id": self.run["run_id"], "finished": _now(), "wall_s": self.elapsed()} | result
        _dump(self.root / "result.json", final)
        return final


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def load_bundle(root: Path) -> dict[str, Any]:
    out: dict[str, Any] = {"root": str(root)}
    for name in ("run", "result", "assertions"):
        p = root / f"{name}.json"
        out[name] = json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    actions = root / "actions.jsonl"
    out["actions"] = (
        [json.loads(line) for line in actions.read_text(encoding="utf-8").splitlines() if line.strip()]
        if actions.exists()
        else []
    )
    shots = sorted((root / "screenshots").glob("*.png")) if (root / "screenshots").exists() else []
    out["screenshots"] = [s.name for s in shots]
    return out
