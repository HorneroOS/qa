from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PIL import Image

from hornero_qa.cli import main
from hornero_qa.evidence import load_bundle
from hornero_qa.importer import EvidenceImportError, ImportRequest, import_evidence
from hornero_qa.scenario import Scenario, load, resolve
from hornero_qa.vision import frame_sha256
from tests.conftest import desktop

ISO_SHA = "b8cd0f8604bc69f7d2112fb8bccd97115d32d197e9c92c62e02faf5de6345aec"
STARTED = datetime(2026, 11, 4, 11, 11, tzinfo=UTC)
FINISHED = datetime(2026, 11, 4, 11, 35, tzinfo=UTC)


def _scenario() -> Scenario:
    return load(resolve("install/desktop-uefi-unencrypted"))


def _source(tmp_path: Path, *, result: str = "# Result\n\nEverything PASS PASS PASS.\n") -> Path:
    src = tmp_path / "preview00-desktop"
    src.mkdir()
    (src / "RESULT.md").write_text(result, encoding="utf-8")
    Image.fromarray(desktop()).save(src / "00-live.png")
    Image.fromarray(desktop(seed=3)).save(src / "18 Desktop!.png")
    return src


def _request(tmp_path: Path, src: Path, **overrides: object) -> ImportRequest:
    base: dict[str, object] = {
        "source": src,
        "scenario": _scenario(),
        "verdict": "inconclusive",
        "reason": "manual checklist does not record every scenario proof probe",
        "product": {"iso": "horneroos-test.iso", "iso_sha256": ISO_SHA, "installer_sha": "abc123"},
        "runs_dir": tmp_path / "runs",
        "started": STARTED,
        "finished": FINISHED,
    }
    base.update(overrides)
    return ImportRequest(**base)  # type: ignore[arg-type]


def test_import_builds_complete_bundle_without_parsing_prose(tmp_path: Path) -> None:
    src = _source(tmp_path)
    root = import_evidence(_request(tmp_path, src))

    assert root.name == "20261104T111100Z-install-desktop-uefi-unencrypted-1"
    loaded = load_bundle(root)
    # RESULT.md prose says PASS; the explicit verdict wins.
    assert loaded["result"]["verdict"] == "inconclusive"
    assert loaded["result"]["class"] == "inconclusive"
    assert loaded["result"]["reason"].startswith("manual checklist")
    assert loaded["result"]["wall_s"] == 24 * 60
    assert loaded["run"]["schema"] == "hornero.qa.run/1"
    assert loaded["run"]["scenario"] == "install/desktop-uefi-unencrypted"
    assert loaded["run"]["product"]["iso_sha256"] == ISO_SHA
    assert loaded["run"]["product"]["installer_sha"] == "abc123"
    assert (root / "logs" / "RESULT.md").read_bytes() == (src / "RESULT.md").read_bytes()
    assert load(root / "scenario.yaml").id == loaded["run"]["scenario"]
    assert loaded["screenshots"] == ["001-live.png", "002-desktop.png"]
    for name in loaded["screenshots"]:
        shot = root / "screenshots" / name
        sidecar = json.loads(shot.with_suffix(".json").read_text())
        assert sidecar["schema"] == "hornero.qa.screenshot/1"
        assert sidecar["sha256"] == frame_sha256(shot)
        assert sidecar["run_id"] == root.name
        assert sidecar["environment"]["captured_resolution"] == "320x200"
    sidecar = json.loads((root / "screenshots" / "002-desktop.json").read_text())
    assert sidecar["source_file"] == "18 Desktop!.png"
    # One honest manual assertion; no invented probe results.
    assert len(loaded["assertions"]) == 1
    assert loaded["assertions"][0]["kind"] == "manual"
    assert loaded["assertions"][0]["detail"] == "logs/RESULT.md"
    assert [a["kind"] for a in loaded["actions"]] == ["manual-run", "import"]
    assert "INCONCLUSIVE" in (root / "report.html").read_text()


def test_import_rejects_missing_result_md(tmp_path: Path) -> None:
    src = _source(tmp_path)
    (src / "RESULT.md").unlink()
    with pytest.raises(EvidenceImportError, match=r"RESULT\.md"):
        import_evidence(_request(tmp_path, src))


def test_import_rejects_no_screenshots_and_bad_png(tmp_path: Path) -> None:
    src = _source(tmp_path)
    for png in src.glob("*.png"):
        png.unlink()
    with pytest.raises(EvidenceImportError, match="at least one"):
        import_evidence(_request(tmp_path, src))
    (src / "00-fake.png").write_bytes(b"not a png")
    with pytest.raises(EvidenceImportError, match="not a valid PNG"):
        import_evidence(_request(tmp_path, src))


def test_import_rejects_bad_inputs(tmp_path: Path) -> None:
    src = _source(tmp_path)
    with pytest.raises(EvidenceImportError, match="verdict"):
        import_evidence(_request(tmp_path, src, verdict="passed"))
    with pytest.raises(EvidenceImportError, match="iso_sha256"):
        import_evidence(_request(tmp_path, src, product={"iso": "x.iso", "iso_sha256": "XYZ"}))
    with pytest.raises(EvidenceImportError, match="finished"):
        import_evidence(_request(tmp_path, src, finished=STARTED.replace(hour=10)))


def test_import_refuses_to_overwrite(tmp_path: Path) -> None:
    src = _source(tmp_path)
    import_evidence(_request(tmp_path, src))
    with pytest.raises(EvidenceImportError, match="already exists"):
        import_evidence(_request(tmp_path, src))


def test_import_failed_bundle_leaves_no_partial(tmp_path: Path) -> None:
    src = _source(tmp_path)
    scenario = _scenario()
    scenario.text = ""
    scenario.source = None
    with pytest.raises(EvidenceImportError, match="no source text"):
        import_evidence(_request(tmp_path, src, scenario=scenario))
    assert not list((tmp_path / "runs").glob("*"))


def test_import_cli_roundtrip_and_unknown_scenario(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    src = _source(tmp_path)
    runs = tmp_path / "runs"
    argv = [
        "import",
        str(src),
        "--scenario",
        "install/desktop-uefi-unencrypted",
        "--verdict",
        "pass",
        "--reason",
        "operator executed every scenario proof; see RESULT.md",
        "--iso",
        "horneroos-test.iso",
        "--iso-sha256",
        ISO_SHA,
        "--product",
        "installer_sha=abc123",
        "--runs-dir",
        str(runs),
        "--started",
        "2026-11-04T11:11:00Z",
        "--finished",
        "2026-11-04T11:35:00Z",
    ]
    assert main(argv) == 0
    bundle = Path(capsys.readouterr().out.strip())
    assert load_bundle(bundle)["result"]["verdict"] == "pass"

    bad = list(argv)
    bad[bad.index("install/desktop-uefi-unencrypted")] = "install/no-such-scenario"
    assert main(bad) == 64
