from __future__ import annotations

import re
from pathlib import Path

from hornero_qa.scenario import SCENARIO_DIR

# Install scenarios execute their proofs on a clean system installed from the
# candidate ISO. That composition does not ship jq (it is only in the server
# package set of the canonical catalogue), so an install probe that pipes
# through jq can never pass as written (HorneroOS/qa#63). Other scenario
# families run inside the provisioned QA image and keep their own contract.
_JQ = re.compile(r"(?<![\w-])jq(?![\w-])")


def _install_scenario_texts() -> list[tuple[Path, str]]:
    return [
        (path, path.read_text(encoding="utf-8")) for path in sorted((SCENARIO_DIR / "install").glob("*.yaml"))
    ]


def test_install_scenarios_do_not_depend_on_jq() -> None:
    offenders = [str(path) for path, text in _install_scenario_texts() if _JQ.search(text)]
    assert offenders == [], f"install scenarios must be jq-free (qa#63): {offenders}"


def test_install_scenarios_exist() -> None:
    assert len(_install_scenario_texts()) >= 8
