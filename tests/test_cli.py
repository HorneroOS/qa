from __future__ import annotations

import pytest

from hornero_qa.cli import main


def test_help_runs() -> None:
    assert main([]) == 0


def test_list_and_validate(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["list"]) == 0
    assert "smoke/desktop-ready" in capsys.readouterr().out
    assert main(["validate"]) == 0


def test_unknown_scenario_is_usage_error(tmp_path_factory: pytest.TempPathFactory) -> None:
    img = tmp_path_factory.mktemp("img") / "x.qcow2"
    img.write_bytes(b"")
    assert main(["run", "no/such-scenario", "--image", str(img)]) == 64
