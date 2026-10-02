"""Promote certified screenshots to product media (website build input).

Only frames from PASS runs, and only the names a scenario lists under
`media`, are exported. Every file keeps its provenance sidecar and is
re-hashed on export, so a consumer can verify what it publishes.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

import yaml

from hornero_qa.evidence import load_bundle
from hornero_qa.vision import frame_sha256

MANIFEST_SCHEMA = "hornero.qa.media/1"
_SEQ = re.compile(r"^\d{3}-")


class MediaError(ValueError):
    pass


def export(bundles: list[Path], out: Path) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for root in bundles:
        b = load_bundle(root)
        run, res = b["run"] or {}, b["result"] or {}
        if res.get("verdict") != "pass":
            raise MediaError(f"{root}: verdict {res.get('verdict')!r}; only passing runs are promoted")
        scenario = yaml.safe_load((root / "scenario.yaml").read_text(encoding="utf-8")) or {}
        wanted = set(scenario.get("media", []))
        for shot in b["screenshots"]:
            name = _SEQ.sub("", Path(shot).stem)
            if name not in wanted:
                continue
            src = root / "screenshots" / shot
            sidecar = json.loads(src.with_suffix(".json").read_text(encoding="utf-8"))
            digest = frame_sha256(src)
            if digest != sidecar.get("sha256"):
                raise MediaError(f"{src}: sha256 does not match its sidecar")
            dest = out / run["scenario"] / f"{name}.png"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
            shutil.copyfile(src.with_suffix(".json"), dest.with_suffix(".json"))
            items.append(
                {
                    "file": dest.relative_to(out).as_posix(),
                    "sha256": digest,
                    "scenario": run["scenario"],
                    "run_id": run["run_id"],
                    "product": run.get("product", {}),
                }
            )
    manifest = {"schema": MANIFEST_SCHEMA, "items": sorted(items, key=lambda i: i["file"])}
    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest
